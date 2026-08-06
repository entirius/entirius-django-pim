# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import json
import warnings
from datetime import datetime

from django.core.exceptions import ObjectDoesNotExist
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone
from django_regional.models import Language
from django_utils.tools import prefix_idx
from idx_normalizator import normalize_idx, normalize_url_key
from process_logger import ProcessLoggerMixin
from slugify import slugify
from urllib3.exceptions import InsecureRequestWarning

from django_pim.managers import PictureManager
from django_pim.models import (
    Attribute,
    BundleLink,
    BundleSection,
    ConfigurableLink,
    Feature,
    FeatureInFeatureSet,
    FeatureScopeEnum,
    FeatureSet,
    FeatureTypeEnum,
    FrontendInputTypeEnum,
    KindOfProductEnum,
    Picture,
    PictureRoleEnum,
    Product,
    ProductAttribute,
    ProductBundle,
    ProductCategory,
    ProductClassEnum,
    ProductConfigurable,
    ProductCustom,
    ProductInCategory,
    ProductPicture,
    ProductSimple,
    ProductVariantGroup,
    ProductVariantGroupProduct,
    ProductVideo,
    ProductVisibilityEnum,
    RealProduct,
    Shop,
    Video,
    VideoRoleEnum,
)


class DbConnect:
    def execute(self, sql: str, params: dict):
        with connection.cursor() as cursor:
            cursor.execute(sql, params)


class DjangoPimRepository(ProcessLoggerMixin):
    name = "django_pim"
    locale: str
    feature_set_default: FeatureSet
    last_feature_position_in_default_feature_set: int = 0
    shop: Shop
    # Caches initialized in __init__ (instance-level, not shared between instances)
    db_connect: DbConnect
    BULK_BATCH_SIZE: int = 1000

    def __init__(self):
        super().__init__()
        from process_logger import ProcessLogger

        if not hasattr(self, "logger") or self.logger is None:
            self.logger = ProcessLogger(process_name="django_pim_repository", module="django_pim")
        self.feature_set_default, _ = FeatureSet.objects.get_or_create(idx="default")
        self.db_connect = DbConnect()
        self.shop = None
        self.features_cache: dict[str, Feature] = {}
        self.attributes_cache: dict[str, dict[str, Attribute]] = {}
        self.products_cache: dict[tuple[str, int], Product] = {}
        self.feature_set_magento_cache: dict[int, FeatureSet] = {}
        self.products_magento_cache: dict[int, Product] = {}
        self.features_magento_cache: dict[int, Feature] = {}

    def set_shop(self, channel_idx: str):
        shop = Shop.objects.filter(idx=channel_idx).first()
        if shop is None:
            # Leaving self.shop None turns every `filter(shop=self.shop)` below into
            # `shop_id IS NULL`: reads return nothing and the variant-group full replace
            # deletes nothing, then fails on insert. Fail here instead, at the choke point.
            raise ValueError(f"Channel with idx={channel_idx!r} does not exist")
        self.shop = shop
        # Both product caches are shop-scoped but keyed without the shop, so a stale
        # entry would serve the previous shop's Product for the same SKU / magento_pk.
        self.products_cache.clear()
        self.products_magento_cache.clear()

    def diff_update(self, entity, attribute, data, need_save: list):
        if getattr(entity, attribute) != data:
            setattr(entity, attribute, data)
            need_save.append(attribute)
        return entity

    def add_feature_to_cache(self, feature: Feature) -> None:
        self.features_cache[feature.idx] = feature

    def get_feature_from_cache(self, feature_idx: str) -> Feature | None:
        return self.features_cache.get(feature_idx, None)

    def add_attribute_to_cache(self, feature_idx: str, attribute: Attribute) -> None:
        if feature_idx not in self.attributes_cache:
            self.attributes_cache[feature_idx] = {}
        self.attributes_cache[feature_idx][attribute.idx] = attribute

    def get_attribute_from_cache(self, feature_idx: str, attribute_idx: str) -> Attribute | None:
        if feature_idx in self.attributes_cache:
            return self.attributes_cache[feature_idx].get(attribute_idx, None)
        return None

    def real_product_update_or_create(
        self, sku: str, ean: str | None = None, kind_of_product: int = KindOfProductEnum.ProductVirtual
    ) -> RealProduct:
        try:
            real_product = RealProduct.objects.get(sku=sku)
            need_save = []
            real_product = self.diff_update(real_product, "ean", ean, need_save)
            real_product = self.diff_update(real_product, "kind_of_product", kind_of_product, need_save)
            if len(need_save) > 0:
                real_product.save(ignore_validate_ean=True)
                self.logger.add_log_param_once("updated_fields", need_save)
                self.logger.set_db_operation("UPDATE", self.name, "RealProduct")
                self.logger.set_code(None)
                self.logger.info(f"RealProduct saved with sku: {sku}")
        except ObjectDoesNotExist:
            real_product = RealProduct(sku=sku, ean=ean, kind_of_product=kind_of_product)
            real_product.save(ignore_validate_ean=True)
            self.logger.set_db_operation("CREATE", self.name, "RealProduct")
            self.logger.set_code(None)
            self.logger.info(f"RealProduct saved with sku: {sku}")

        return real_product

    def real_product_bulk_update_or_create(
        self, real_products: dict[str, RealProduct], updated_at: datetime | None = None
    ) -> tuple[dict[str, RealProduct], dict[str, RealProduct]]:
        create = real_products
        update = {}
        result = RealProduct.objects.filter(sku__in=real_products.keys())
        for rp_in_db in result:
            rp_in_db.ean = real_products[rp_in_db.sku].ean
            rp_in_db.kind_of_product = real_products[rp_in_db.sku].kind_of_product
            update[rp_in_db.sku] = rp_in_db
            create.pop(rp_in_db.sku)

        created = {}
        if len(create) > 0:
            self.logger.set_db_operation("BULK_CREATE", self.name, "RealProduct")
            rps = RealProduct.objects.bulk_create(create.values(), batch_size=self.BULK_BATCH_SIZE)
            for rp in rps:
                created[rp.sku] = rp
            self.logger.set_code(None)
            self.logger.info(f"RealProducts created in bulk: {len(create)}")

        if len(update) > 0:
            self.logger.set_db_operation("BULK_UPDATE", self.name, "RealProduct")
            bulk_update_kwargs = {"fields": ["ean", "kind_of_product"], "batch_size": self.BULK_BATCH_SIZE}

            updated = RealProduct.objects.bulk_update(update.values(), **bulk_update_kwargs)
            self.logger.set_code(None)
            self.logger.info(f"RealProducts updated in bulk: {updated}")

        return created, update

    def product_simple_update_or_create(
        self, real_product: RealProduct, updated_at: datetime, update: bool = True
    ) -> ProductSimple:
        try:
            ps: ProductSimple = ProductSimple.objects.get(shop=self.shop, real_product=real_product)
            need_save = []
            if update:
                ps = self.diff_update(ps, "is_enabled", True, need_save)
                ps = self.diff_update(ps, "updated_at", updated_at, need_save)
            if len(need_save) > 0:
                ps.save()
                self.logger.add_log_param_once("updated_fields", need_save)
                self.logger.set_db_operation("UPDATE", self.name, "ProductSimple")
                self.logger.set_code(None)
                self.logger.info(f"ProductSimple saved with sku: {real_product.sku}")
        except ObjectDoesNotExist:
            ps = ProductSimple(
                shop=self.shop,
                real_product=real_product,
                is_enabled=True,
                feature_set=self.feature_set_default,
                updated_at=updated_at,
                visibility=ProductVisibilityEnum.CATALOG_AND_SEARCH,
            )
            ps.save()
            self.logger.set_db_operation("CREATE", self.name, "ProductSimple")
            self.logger.set_code(None)
            self.logger.info(f"ProductSimple saved with sku: {real_product.sku}")

        return ps

    def product_bulk_update_or_create(
        self,
        products: dict[str, Product],
        update: list = None,
        product_class: int = ProductClassEnum.ProductSimple,
        check_product_class: bool = True,
        updated_at: datetime | None = None,
    ) -> tuple[dict[str, Product], dict[str, Product], int]:
        """
        Bulk update or create products with timestamp-based conditional update.

        Args:
            products: Dictionary of products to create/update (keyed by SKU)
            update: List of field names to update
            product_class: Product class to filter by
            check_product_class: Whether to check product class matches
            updated_at: Timestamp for conditional update (only update if DB record is older)
                       If None, updates unconditionally (backward compatibility)

        Returns:
            Tuple of (created_dict, updated_dict, skipped_count)
            - created_dict: Dictionary of created products
            - updated_dict: Dictionary of updated products
            - skipped_count: Number of products skipped due to timestamp check

        Timestamp-based Protection:
            If updated_at is provided, only updates products where:
            - DB updated_at < new updated_at (update with newer data)
            - OR DB updated_at is NULL (first time setting)
            This prevents race condition where bulk import (old data) overwrites
            journal update (fresh data).
        """
        update = update if update is not None else []
        self.logger.add_log_param("product_class", product_class)
        if updated_at:
            self.logger.add_log_param("updated_at", updated_at.isoformat())

        create = products
        to_update = {}
        skipped_count = 0

        result = Product.objects.prefetch_related("real_product").filter(
            shop=self.shop, real_product__sku__in=products.keys()
        )
        for ps_in_db in result:
            sku = ps_in_db.real_product.sku

            if check_product_class:
                if ps_in_db.product_class != product_class:
                    # Typ produktu zmienił się w źródle (np. simple -> configurable).
                    # Usuwamy stary rekord (kaskadowo starą podklasę MTI i zależności),
                    # zostawiając sku w `create` -> zostanie utworzony na nowo z właściwym typem.
                    self.logger.add_log_param("sku", sku)
                    self.logger.warning(
                        f"Product {sku} exists with other product type "
                        f"({ps_in_db.product_class} -> {product_class}). Recreating with new type."
                    )
                    self.logger.delete_log_param("sku")
                    ps_in_db.delete()
                    continue

            # Proceed with update
            for u in update:
                setattr(ps_in_db, u, getattr(products[sku], u))

            if len(update) > 0:
                ps_in_db.updated_at = products[sku].updated_at
                to_update[sku] = ps_in_db
            create.pop(sku)

        created = {}
        if len(create) > 0:
            self.logger.set_db_operation("BULK_CREATE", self.name, "Product")
            pss = Product.objects.bulk_create(create.values(), batch_size=self.BULK_BATCH_SIZE)
            for ps in pss:
                created[ps.real_product.sku] = ps
            self.logger.set_code(None)
            self.logger.info(f"Product created in bulk: {len(create)}")

        if len(to_update) > 0:
            self.logger.set_db_operation("BULK_UPDATE", self.name, "Product")
            bulk_update_kwargs = {
                "fields": ["is_enabled", "feature_set", "updated_at", "magento_pk"],
                "batch_size": self.BULK_BATCH_SIZE,
            }

            updated = Product.objects.bulk_update(to_update.values(), **bulk_update_kwargs)
            self.logger.set_code(None)
            self.logger.info(f"Product updated in bulk: {updated}")

        if skipped_count > 0:
            self.logger.info(f"Product updates skipped (timestamp check): {skipped_count}")

        self.raw_fill_product_class_by_product(product_class)

        return created, to_update, skipped_count

    def get_product(self, sku: str, product_class: int = ProductClassEnum.ProductSimple) -> Product | None:
        # product_class belongs in the key: the query filters on it, so caching by SKU
        # alone returns the Simple product for a later Bundle lookup of the same SKU.
        cache_key = (sku, product_class)
        try:
            if cache_key not in self.products_cache:
                self.products_cache[cache_key] = Product.objects.get(
                    shop=self.shop, real_product__sku=sku, product_class=product_class
                )
            return self.products_cache[cache_key]
        except ObjectDoesNotExist:
            self.logger.set_code(None)
            self.logger.add_log_param("sku", sku)
            self.logger.warning(f"Product with sku {sku} not found.")
            return None

    def get_all_products_by_attr_filter(self, filters) -> list[Product]:
        return Product.objects.filter(shop=self.shop).filter(*filters)

    def products_simple_get_bulk(self, skus: list[str]):
        return (
            ProductSimple.objects.filter(shop=self.shop, real_product__sku__in=skus)
            .prefetch_related("real_product")
            .iterator(chunk_size=1000)
        )

    def products_bundle_get_bulk(self, skus: list[str]):
        return (
            ProductBundle.objects.filter(shop=self.shop, real_product__sku__in=skus)
            .prefetch_related("real_product")
            .iterator(chunk_size=1000)
        )

    def products_configurable_get_bulk(self, skus: list[str]):
        return (
            ProductConfigurable.objects.filter(shop=self.shop, real_product__sku__in=skus)
            .prefetch_related("real_product")
            .iterator(chunk_size=1000)
        )

    def products_custom_get_bulk(self, skus: list[str]):
        return (
            ProductCustom.objects.filter(shop=self.shop, real_product__sku__in=skus)
            .prefetch_related("real_product")
            .iterator(chunk_size=1000)
        )

    def get_from_cache_or_create_picture_error(
        self, pic_source_url: str, media_type: PictureRoleEnum = None
    ) -> Picture | None:
        picture = None
        try:
            picture = self.get_from_cache_or_create_picture(pic_source_url, media_type)
        except Exception as e:
            self.logger.set_code(None)
            self.logger.exception(e)

        return picture

    def get_from_cache_or_create_picture(
        self, pic_source_url: str, media_type: PictureRoleEnum = None, skip_error: bool = False
    ) -> Picture | None:
        media_type = media_type if media_type else ""

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", InsecureRequestWarning)
            picture, created = PictureManager.download_picture(download_url=pic_source_url, verify_ssl=False)

        if not created and picture:
            self.logger.set_code(None)
            self.logger.info(f"Picture {media_type} got from cache.")

        if created and picture:
            self.logger.set_code(None)
            self.logger.info(f"Picture {media_type} downloaded.")

        if created and not picture:
            self.logger.set_code(None)
            self.logger.warning(f"Picture {media_type} not found in DB")
        return picture

    def get_from_cache_or_create_video(self, video_url: str, title: str) -> Video | None:
        try:
            video = Video.objects.get(video_url=video_url)
            if video.title != title:
                self.logger.set_db_operation("UPDATE", self.name, "Video")
                video.title = title
                video.save()
        except ObjectDoesNotExist:
            self.logger.set_db_operation("CREATE", self.name, "Video")
            video = Video(video_url=video_url, title=title)
            video.save()
        except Exception as e:
            self.logger.set_code(None)
            self.logger.exception(e)
            video = None

        return video

    def save_product_picture(
        self,
        product: Product,
        picture: Picture,
        media_type: PictureRoleEnum,
        position: int,
        language: str | Language | None = None,
        update_main: bool = True,
    ) -> ProductPicture | None:
        pp = None
        try:
            if isinstance(language, Language):
                lang = language
            else:
                lang = Language.objects.get(iso2=language) if language else None
        except ObjectDoesNotExist:
            self.logger.set_code(None)
            self.logger.warning(f"Language {language} not found. Can't import pictures.")
            return pp

        try:
            self.logger.set_db_operation("UPDATE", self.name, "ProductPicture")
            if media_type == PictureRoleEnum.MAIN:
                qs = ProductPicture.objects.filter(product=product, picture_role=media_type, language=lang)
            else:
                qs = ProductPicture.objects.filter(product=product, picture=picture, language=lang)

            pp = qs.order_by("pk").first()
            if pp is None:
                raise ObjectDoesNotExist
            # Defensywnie usuń ewentualne duplikaty (zostaw najstarszy) - inaczej .get() rzuca MultipleObjectsReturned
            qs.exclude(pk=pp.pk).delete()

            if media_type == PictureRoleEnum.MAIN:
                save = False
                if pp.picture != picture and update_main:
                    pp.picture = picture
                    save = True
                if pp.position != position and update_main:
                    pp.position = position
                    save = True
                if save:
                    pp.save()
            else:
                pp.picture_role = media_type
                pp.position = position
                pp.save()
        except ObjectDoesNotExist:
            self.logger.set_db_operation("CREATE", self.name, "ProductPicture")
            pp = ProductPicture(
                product=product, picture=picture, position=position, picture_role=media_type, language=lang
            )
            pp.save()
        except Exception as e:
            self.logger.set_code(None)
            self.logger.exception(e)

        return pp

    def delete_product_picture_old(
        self, product: Product, product_pictures: list[ProductPicture], language: str | None = None
    ) -> None:
        lang_filter = Q(Q(language__iso2=language) | Q(language__isnull=True)) if language else Q(language__isnull=True)
        pp_to_delete = ProductPicture.objects.filter(Q(product=product) & lang_filter).exclude(
            id__in=[pp.id for pp in product_pictures if pp is not None]
        )
        pp_to_delete.delete()

        self.logger.set_code(None)
        self.logger.info(f"Old pictures deleted for product: {product.sku}")

    def save_product_video(
        self, product: Product, video: Video, media_type: VideoRoleEnum, position: int, language: str | None = None
    ) -> ProductVideo | None:
        pv = None
        try:
            lang = Language.objects.get(iso2=language) if language else None
        except ObjectDoesNotExist:
            self.logger.set_code(None)
            self.logger.warning(f"Language {language} not found. Can't import pictures.")
            return pv

        try:
            self.logger.set_db_operation("UPDATE", self.name, "ProductVideo")
            if media_type == VideoRoleEnum.MAIN:
                pv = ProductVideo.objects.get(product=product, video_role=media_type, language=lang)
                save = False
                if pv.video != video:
                    pv.video = video
                    save = True
                if pv.position != position:
                    pv.position = position
                    save = True
                if save:
                    pv.save()
            else:
                pv = ProductVideo.objects.get(product=product, video=video, language=lang)
                pv.video_role = media_type
                pv.position = position
                pv.save()
        except ObjectDoesNotExist:
            self.logger.set_db_operation("CREATE", self.name, "ProductVideo")
            pv = ProductVideo(product=product, video=video, position=position, video_role=media_type, language=lang)
            pv.save()
        except Exception as e:
            self.logger.set_code(None)
            self.logger.exception(e)

        return pv

    def delete_product_video_old(
        self, product: Product, product_videos: list[ProductVideo], language: str | None = None
    ) -> None:
        lang_query = {"language__iso2": language} if language else {}
        ProductVideo.objects.filter(product=product, **lang_query).exclude(
            id__in=[pp.id for pp in product_videos]
        ).delete()
        self.logger.set_code(None)
        self.logger.info(f"Old videos deleted for product: {product.sku}")

    def raw_fill_product_class_by_product(self, product_class: int = ProductClassEnum.ProductSimple):
        match product_class:
            case ProductClassEnum.ProductSimple:
                table = "django_pim_productsimple"
                columns = "product_ptr_id, quantity"
                select = "p.id, 0"  # quantity not used, hardcode
            case ProductClassEnum.ProductConfigurable:
                table = "django_pim_productconfigurable"
                columns = "product_ptr_id"
                select = "p.id"
            case ProductClassEnum.ProductBundle:
                table = "django_pim_productbundle"
                columns = "product_ptr_id"
                select = "p.id"
            case ProductClassEnum.ProductCustom:
                table = "django_pim_productcustom"
                columns = "product_ptr_id, customization_feature_set_id"
                select = "p.id, 1"  # hardcode
            case _:
                self.logger.debug(f"ProductClass {product_class} don't have its own table.")
                return

        # Najpierw usuwamy rekordy z tabeli dziedziczonej, które nie mają odpowiednika w product z właściwą klasą
        cleanup_sql = (
            f"DELETE FROM {table} "
            f"WHERE product_ptr_id NOT IN (SELECT id FROM django_pim_product WHERE product_class={product_class});"
        )
        self.db_connect.execute(cleanup_sql, {})

        # Teraz dodajemy tylko brakujące rekordy (bez duplikatów)
        fill_sql = (
            f"INSERT INTO {table} ({columns}) "
            f"SELECT {select} FROM django_pim_product p "
            f"WHERE p.product_class={product_class} AND "
            f"NOT EXISTS (SELECT 1 FROM {table} WHERE product_ptr_id = p.id);"
        )
        self.db_connect.execute(fill_sql, {})

    def disable_products(self, updated_at: datetime, product_class: int = ProductClassEnum.ProductSimple) -> None:
        Product.objects.filter(shop=self.shop, product_class=product_class).exclude(updated_at=updated_at).update(
            is_enabled=False
        )
        self.logger.add_log_param_once("updated_at", updated_at.isoformat())
        self.logger.set_db_operation("UPDATE", self.name, "Product")
        self.logger.set_code(None)
        self.logger.info(f"Products with updated_at != {updated_at.isoformat()} disabled")

    def save_product_attribute_value(
        self, product: Product, feature: Feature, value, update: bool = True
    ) -> ProductAttribute:
        self.logger.add_log_param("feature_idx", feature.idx)
        kwargs = self.product_attribute_pass_value_to_kwargs_by_feature_type(feature, value)
        try:
            self.logger.set_db_operation("UPDATE", self.name, "ProductAttribute")
            pa: ProductAttribute = ProductAttribute.objects.get(product=product, feature=feature)
            if update:
                for name, val in kwargs.items():
                    setattr(pa, name, val)
                pa.save()
        except ObjectDoesNotExist:
            self.logger.set_db_operation("CREATE", self.name, "ProductAttribute")
            pa = ProductAttribute(product=product, feature=feature, **kwargs)
            pa.save()
        self.logger.set_code(None)
        self.logger.info(f"Attribute {feature.idx} saved for product: {product.real_product.sku}")

        return pa

    def product_attribute_pass_value_to_kwargs_by_feature_type(self, feature: Feature, value) -> dict:
        kwargs = {}
        if feature.feature_type in [FeatureTypeEnum.VARCHAR255_T9N, FeatureTypeEnum.TEXT_T9N]:
            kwargs = {"value_txt_t9n": value}
        if feature.feature_type in [FeatureTypeEnum.VARCHAR255, FeatureTypeEnum.TEXT]:
            kwargs = {"value_txt": value}
        if feature.feature_type in [FeatureTypeEnum.JSON, FeatureTypeEnum.JSON_T9N]:
            if isinstance(value, str):
                value = json.loads(value)
            kwargs = {"value_json": value}
        if feature.feature_type == FeatureTypeEnum.DECIMAL:
            kwargs = {"value_decimal": value}
        if feature.feature_type == FeatureTypeEnum.DATETIME:
            if value is not None:
                if isinstance(value, str):
                    from datetime import datetime

                    try:
                        value = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        try:
                            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
                        except ValueError:
                            self.logger.warning(f"Could not parse datetime string: {value}")
                            value = None

                if value is not None and hasattr(value, "tzinfo") and value.tzinfo is None:
                    value = timezone.make_aware(value)
            kwargs = {"value_datetime": value}
        if feature.feature_type == FeatureTypeEnum.BOOL:
            if isinstance(value, str):
                match value.lower():
                    case "0":
                        bool_value = False
                    case "1":
                        bool_value = True
                    case "false":
                        bool_value = False
                    case "true":
                        bool_value = True
                    case _:
                        bool_value = False
                value = bool_value
            kwargs = {"value_bool": value}
        if feature.feature_type in [FeatureTypeEnum.SELECT, FeatureTypeEnum.MULTISELECT]:
            raise ValueError("FeatureType SELECT and MULTISELECT given. Use save_product_attribute method for this.")
        return kwargs

    def product_attribute_values_bulk_update_or_create(
        self,
        feature: Feature,
        products_attributes: dict[str, ProductAttribute],
        update: bool = True,
        updated_at: datetime | None = None,
    ) -> tuple[dict[str, ProductAttribute], dict[str, ProductAttribute], int]:
        """
        Bulk update or create product attribute values with timestamp-based conditional update.

        Args:
            feature: Feature to update attributes for
            products_attributes: Dictionary of product attributes (keyed by SKU)
            update: Whether to update existing attributes
            updated_at: Timestamp for conditional update (only update if product is older)
                       If None, updates unconditionally (backward compatibility)

        Returns:
            Tuple of (created_dict, updated_dict, skipped_count)
            - created_dict: Dictionary of created attributes
            - updated_dict: Dictionary of updated attributes
            - skipped_count: Number of attributes skipped due to timestamp check

        Timestamp-based Protection:
            If updated_at is provided, only updates attributes where product.updated_at < new updated_at.
            This prevents race condition where bulk import overwrites fresh journal updates.
        """
        create = products_attributes
        to_update = {}
        skipped_count = 0

        result: list[ProductAttribute] = ProductAttribute.objects.prefetch_related(
            "product", "product__real_product"
        ).filter(feature=feature, product__shop=self.shop, product__real_product__sku__in=products_attributes.keys())
        for in_db in result:
            if in_db.product.sku not in products_attributes:
                self.logger.set_code(None)
                self.logger.warning(f"Product {in_db.product.sku} not found in imported data")
                continue
            if update:
                in_db.value_txt_t9n = products_attributes[in_db.product.sku].value_txt_t9n
                in_db.value_txt = products_attributes[in_db.product.sku].value_txt
                in_db.value_json = products_attributes[in_db.product.sku].value_json
                in_db.value_decimal = products_attributes[in_db.product.sku].value_decimal
                in_db.value_datetime = products_attributes[in_db.product.sku].value_datetime
                in_db.value_bool = products_attributes[in_db.product.sku].value_bool
                to_update[in_db.product.sku] = in_db
            if in_db.product.sku in create:
                create.pop(in_db.product.sku)

        created = {}
        if len(create) > 0:
            self.logger.set_db_operation("BULK_CREATE", self.name, "ProductAttribute")
            objs_created = ProductAttribute.objects.bulk_create(
                create.values(), batch_size=self.BULK_BATCH_SIZE, ignore_conflicts=True
            )
            for obj in objs_created:
                created[obj.product.sku] = obj
            self.logger.set_code(None)
            self.logger.info(f"ProductAttribute for feature {feature.idx} created in bulk: {len(create)}")

        if len(to_update) > 0:
            self.logger.set_db_operation("BULK_UPDATE", self.name, "ProductAttribute")
            bulk_update_kwargs = {
                "fields": ["value_txt_t9n", "value_txt", "value_json", "value_decimal", "value_datetime", "value_bool"],
                "batch_size": self.BULK_BATCH_SIZE,
            }

            updated = ProductAttribute.objects.bulk_update(to_update.values(), **bulk_update_kwargs)
            self.logger.set_code(None)
            self.logger.info(f"ProductAttribute for feature {feature.idx} updated in bulk: {updated}")

        if skipped_count > 0:
            self.logger.info(f"ProductAttribute updates skipped (timestamp check): {skipped_count}")

        return created, to_update, skipped_count

    def product_attribute_bulk_update_or_create(
        self,
        feature: Feature,
        products_attributes: dict[str, dict[str, ProductAttribute]],
        skus: list[str],
        updated_at: datetime | None = None,
    ) -> tuple[dict[str, dict[str, ProductAttribute]], dict[str, dict[str, ProductAttribute]]]:
        create = products_attributes
        update = {}
        result: list[ProductAttribute] = ProductAttribute.objects.prefetch_related(
            "product", "product__real_product", "attribute"
        ).filter(feature=feature, product__shop=self.shop, product__real_product__sku__in=skus)
        for in_db in result:
            if in_db.product.sku not in products_attributes:
                continue
            if in_db.attribute.idx not in products_attributes[in_db.product.sku]:
                continue
            in_db.attribute = products_attributes[in_db.product.sku][in_db.attribute.idx].attribute

            if in_db.product.sku not in update:
                update[in_db.product.sku] = {}
            update[in_db.product.sku][in_db.attribute.idx] = in_db
            create[in_db.product.sku].pop(in_db.attribute.idx)
            if len(create[in_db.product.sku]) == 0:
                create.pop(in_db.product.sku)

        created = {}
        if len(create) > 0:
            self.logger.set_db_operation("BULK_CREATE", self.name, "ProductAttribute")
            to_create = []
            for sku, attributes in create.items():
                for attribute in attributes.values():
                    to_create.append(attribute)
            objs_created = ProductAttribute.objects.bulk_create(
                to_create, batch_size=self.BULK_BATCH_SIZE, ignore_conflicts=True
            )
            for obj in objs_created:
                if obj.product.sku not in created:
                    created[obj.product.sku] = {}
                created[obj.product.sku][obj.attribute.idx] = obj
            self.logger.set_code(None)
            self.logger.info(f"ProductAttribute for feature {feature.idx} created in bulk: {len(to_create)}")

        if len(update) > 0:
            self.logger.set_db_operation("BULK_UPDATE", self.name, "ProductAttribute")
            to_update = []
            for sku, attributes in update.items():
                for attribute in attributes.values():
                    to_update.append(attribute)

            bulk_update_kwargs = {"fields": ["attribute"], "batch_size": self.BULK_BATCH_SIZE}
            updated = ProductAttribute.objects.bulk_update(to_update, **bulk_update_kwargs)
            self.logger.set_code(None)
            self.logger.info(f"ProductAttribute for feature {feature.idx} updated in bulk: {len(to_update)}")

        if len(create) == 0 and len(update) == 0:
            self.logger.set_code(None)
            self.logger.warning(f"ProductAttribute for feature {feature.idx} saved in bulk: 0")

        return created, update

    def feature_get_or_create(
        self,
        idx: str,
        name: str | None = None,
        name_t9n: dict[str, str] | None = None,
        feature_set: FeatureSet | None = None,
        feature_type: int = FeatureTypeEnum.VARCHAR255,
        scope: int = FeatureScopeEnum.BUSINESS_UNIT,
        position: int | None = None,
        in_feature_set_position: int | None = None,
        update: bool = True,
        create: bool = True,
        prefix: bool = True,
        cache: bool = True,
    ) -> Feature | None:
        if feature_set is None:
            feature_set = self.feature_set_default

        idx = normalize_idx(str(idx))
        self.logger.add_log_param("feature_idx", idx)
        if prefix:
            idx = prefix_idx(idx, "ftr")
            self.logger.add_log_param_once("feature_prefix_idx", idx)

        cached = self.get_feature_from_cache(idx)
        if cached and not update:
            self.logger.delete_log_param("feature_idx")
            if prefix:
                self.logger.delete_log_param("feature_prefix_idx")
            return cached

        try:
            feature = Feature.objects.get(scope=scope, idx=idx)
            if not update:
                self.add_feature_to_cache(feature)
                return feature

            if name is None and name_t9n is None and not feature.name_t9n:
                name = idx

            self.logger.set_db_operation("UPDATE", self.name, "Feature")
            if name:
                feature.name_t9n = self.replace_t9n(feature.name_t9n, self.locale, name)
            else:
                if name_t9n:
                    for lang, name in name_t9n.items():
                        feature.name_t9n = self.replace_t9n(feature.name_t9n, lang, name)
            feature.feature_type = feature_type
            if position is not None:
                feature.display_order = position
            if feature_type in [FeatureTypeEnum.SELECT, FeatureTypeEnum.MULTISELECT]:
                feature.frontend_input_type = FrontendInputTypeEnum.SELECT_SWATCH_TEXT
            else:
                feature.frontend_input_type = FrontendInputTypeEnum.DEFAULT
            feature.save()
        except ObjectDoesNotExist:
            if not create:
                return None
            self.logger.set_db_operation("CREATE", self.name, "Feature")
            if name:
                name_t9n = {self.locale: name} if name else {self.locale: ""}
            else:
                name_t9n = name_t9n or {self.locale: idx}
            feature = Feature(scope=scope, idx=idx, feature_type=feature_type, name_t9n=name_t9n)
            if position is not None:
                feature.display_order = position
            if feature_type in [FeatureTypeEnum.SELECT, FeatureTypeEnum.MULTISELECT]:
                feature.frontend_input_type = FrontendInputTypeEnum.SELECT_SWATCH_TEXT
            else:
                feature.frontend_input_type = FrontendInputTypeEnum.DEFAULT
            feature.save()
            FeatureInFeatureSet.objects.update_or_create(feature_set=self.feature_set_default, feature=feature)

        in_feature_set_position = in_feature_set_position if in_feature_set_position else 500
        FeatureInFeatureSet.objects.get_or_create(
            feature_set=feature_set, feature=feature, defaults={"position": in_feature_set_position}
        )
        self.logger.set_code(None)
        self.logger.info(
            f"Feature saved with idx: {idx}. Link with feature set FeatureInFeatureSet: {feature_set.idx} also saved."
        )
        if cache:
            self.add_feature_to_cache(feature)
        return feature

    def attribute_get_or_create(
        self,
        idx: str,
        feature: Feature,
        name: str | None = None,
        name_t9n: dict[str, str] | None = None,
        display_order: int | None = None,
        update: bool = True,
        create: bool = True,
        prefix: bool = True,
        cache: bool = True,
    ) -> Attribute | None:
        if not display_order:
            display_order = 100

        if name_t9n is None:
            name_t9n = {}

        if create and (name_t9n is None and name is None):
            raise ValueError("name_t9n or name is required for create and update operation.")

        idx = normalize_idx(str(idx))
        self.logger.add_log_param("attribute_idx", idx)
        if prefix:
            idx = prefix_idx(idx, "attr")
            self.logger.add_log_param_once("attribute_prefix_idx", idx)

        cached = self.get_attribute_from_cache(feature.idx, idx)
        if cached and not update:
            self.logger.delete_log_param("attribute_idx")
            if prefix:
                self.logger.delete_log_param("attribute_prefix_idx")
            return cached

        try:
            self.logger.set_db_operation("UPDATE", self.name, "Attribute")
            attribute: Attribute = Attribute.objects.get(idx=idx, feature=feature)
            if not update:
                self.add_attribute_to_cache(feature.idx, attribute)
                return attribute
            if name:
                attribute.name_t9n = self.replace_t9n(attribute.name_t9n, self.locale, name)
            else:
                if name_t9n:
                    attribute.name_t9n = name_t9n
            attribute.display_order = display_order
            attribute.save()
        except ObjectDoesNotExist:
            if not create:
                return None
            if name:
                name_t9n = {self.locale: name} if name else {self.locale: ""}
            self.logger.set_db_operation("CREATE", self.name, "Attribute")
            attribute = Attribute(feature=feature, idx=idx, name_t9n=name_t9n, display_order=display_order)
            attribute.save()
        self.logger.set_code(None)
        self.logger.info(f"Attribute saved with idx: {idx}")
        if cache:
            self.add_attribute_to_cache(feature.idx, attribute)
        return attribute

    def attribute_get_by_magento_pk(self, magento_pk: int, feature: Feature) -> Attribute | None:
        try:
            return Attribute.objects.get(magento_pk=magento_pk, feature=feature)
        except ObjectDoesNotExist:
            return None

    def save_product_attribute(
        self, product: Product, feature: Feature, attribute: Attribute, cleanup: bool = True
    ) -> ProductAttribute | None:
        if cleanup:
            self.clean_product_attributes(product, feature)

        self.logger.add_log_param("sku", product.sku)
        self.logger.add_log_param("feature_idx", feature.idx)
        self.logger.add_log_param("attribute_idx", attribute.idx)

        self.logger.set_db_operation("CREATE", self.name, "ProductAttribute")
        try:
            pa = ProductAttribute(product=product, feature=feature, attribute=attribute)
            pa.save()
            self.logger.set_code(None)
            self.logger.info(f"Attribute {feature.idx} {attribute.idx} saved for product: {product.real_product.sku}")
        except ValueError as ve:
            self.logger.set_code(None)
            self.logger.warning(ve)
            pa = None

        return pa

    def clean_product_attributes(self, product: Product, feature: Feature) -> None:
        ProductAttribute.objects.filter(product=product, feature=feature).delete()
        self.logger.set_code(None)
        self.logger.debug(
            f"Cleaning all multiselect Attributes before new Save for "
            f"product {product.real_product.sku} and feature {feature.idx}"
        )

    def clean_product_attributes_bulk(self, feature: Feature, skus: list[str]) -> None:
        def divide_chunks(data, n):
            for i in range(0, len(data), n):
                yield data[i : i + n]

        if feature.feature_type not in [FeatureTypeEnum.SELECT, FeatureTypeEnum.MULTISELECT]:
            return

        skus_in_chunks = divide_chunks(skus, self.BULK_BATCH_SIZE)
        for chunk_skus in skus_in_chunks:
            ProductAttribute.objects.filter(
                product__shop=self.shop, product__real_product__sku__in=chunk_skus, feature=feature
            ).delete()

        self.logger.set_code(None)
        self.logger.debug(f"Cleaning all select/multiselect Attributes before new Save for feature {feature.idx}")

    def delete_old_attributes(self, feature: Feature, existing_idxs: list[str]):
        Attribute.objects.filter(feature=feature).exclude(idx__in=existing_idxs).delete()

        self.logger.set_code(None)
        self.logger.debug("Cleaning all select/multiselect old Attributes.")

    def normalize_category_idx(self, category_idx) -> str:
        return ProductCategory.normalize_idx(category_idx)

    def replace_t9n(self, field, locale, new_value):
        if new_value:
            field[locale] = str(new_value)
        else:
            field[locale] = ""
        return field

    def generate_url_key(self, name: str, idx: str | None = None, append_idx=False, max_length: int = 200):
        slug = slugify(name)
        if idx and append_idx:
            url_key = "%s-%s" % (slug[: max_length - len(idx)], str(idx))
        else:
            url_key = slug[:max_length]

        return normalize_url_key(url_key)

    def get_categories(self, root_category: ProductCategory) -> list[ProductCategory]:
        def check_root(category: ProductCategory):
            if category.parent_category is None:
                return False
            if category.parent_category.idx == root_category.idx:
                return True
            else:
                return check_root(category.parent_category)

        categories = []
        pcs = ProductCategory.objects.filter(shop=self.shop).exclude(parent_category__isnull=True)
        for pc in pcs:
            pc: ProductCategory
            if check_root(pc):
                categories.append(pc)

        return categories

    def category_update_or_create(
        self,
        idx: str,
        name: str | None = None,
        name_t9n: dict[str, str] | None = None,
        url_key_t9n: dict[str, str] | None = None,
        is_in_menu: bool | None = None,
        is_active: bool | None = None,
        parent_category: ProductCategory | None = None,
        description_t9n: dict[str, str] | None = None,
        rich_content: dict | None = None,
        position: int = 0,
        clear_url_key_when_inactive: bool = False,
        clear_url_key: bool = None,
    ):
        self.logger.add_log_param("category_idx", idx)
        try:
            pc: ProductCategory = ProductCategory.objects.get(idx=idx, shop=self.shop)
            if is_in_menu is not None:
                pc.is_in_menu = is_in_menu
            if is_active is not None:
                pc.is_active = is_active
            pc.parent_category = parent_category
            if name:
                pc.name_t9n = self.replace_t9n(pc.name_t9n, self.locale, name)
            else:
                pc.name_t9n = name_t9n
            pc.description_t9n = description_t9n

            if not url_key_t9n.get(self.locale, None):
                url_key = self.generate_url_key(name if name else idx, idx=idx, append_idx=True)
            else:
                url_key = url_key_t9n.get(self.locale, None)

            if clear_url_key and clear_url_key_when_inactive:
                url_key_t9n = self.replace_t9n(pc.url_key_t9n, self.locale, "")
            else:
                url_key_t9n = self.replace_t9n(pc.url_key_t9n, self.locale, url_key)

            pc.url_key_t9n = url_key_t9n
            if rich_content is not None:
                if pc.rich_content is None:
                    pc.rich_content = {}
                for rck, rcv in rich_content.items():
                    pc.rich_content[rck] = rcv
            pc.position = position
            pc.save()
            self.logger.set_db_operation("UPDATE", self.name, "ProductCategory")
        except ProductCategory.DoesNotExist:
            if name:
                name_t9n = {self.locale: name} if name else {self.locale: ""}

            if not url_key_t9n.get(self.locale, None):
                url_key = self.generate_url_key(name if name else idx, idx=idx, append_idx=True)
            else:
                url_key = url_key_t9n.get(self.locale, None)

            if clear_url_key and clear_url_key_when_inactive:
                url_key_t9n = self.replace_t9n({}, self.locale, "")
            else:
                url_key_t9n = self.replace_t9n({}, self.locale, url_key)

            pc: ProductCategory = ProductCategory(
                idx=idx,
                name_t9n=name_t9n,
                description_t9n=description_t9n,
                url_key_t9n=url_key_t9n,
                parent_category=parent_category,
                shop=self.shop,
                rich_content=rich_content,
                position=position,
            )
            if is_in_menu is not None:
                pc.is_in_menu = is_in_menu
            if is_active is not None:
                pc.is_active = is_active
            pc.save()
            self.logger.set_db_operation("CREATE", self.name, "ProductCategory")

        self.logger.set_code(None)
        self.logger.info(f"Category saved with idx: {idx}")
        self.logger.delete_log_param("category_idx")
        return pc

    def product_category_bulk_update_or_create(
        self, products_categories: dict[str, ProductInCategory], update_position: bool = True
    ) -> None:
        create = products_categories

        fields = ["position", "updated_at"] if update_position else ["updated_at"]
        self.logger.set_db_operation("BULK_UPDATE_OR_CREATE", self.name, "ProductInCategory")
        ProductInCategory.objects.bulk_create(
            create.values(),
            batch_size=self.BULK_BATCH_SIZE,
            update_conflicts=True,
            unique_fields=["product", "category"],
            update_fields=fields,
        )
        self.logger.set_code(None)
        self.logger.info(f"ProductInCategory created in bulk: {len(create)}")

    def clean_product_category_bulk(self, updated_at: datetime) -> None:
        ProductInCategory.objects.filter(category__shop=self.shop).exclude(updated_at=updated_at).delete()
        self.logger.set_db_operation("DELETE", self.name, "ProductInCategory")
        self.logger.set_code(None)
        self.logger.info("ProductInCategory cleared in bulk")

    def get_products_attributes(self, feature: Feature, skus: list[str] = None):
        query = {"product__real_product__sku__in": skus} if skus else {}
        return (
            ProductAttribute.objects.filter(feature=feature, product__shop=self.shop, **query)
            .prefetch_related("product__real_product", "attribute")
            .iterator(chunk_size=10000)
        )

    def get_bundle_section_default(self) -> tuple[BundleSection, bool]:
        return BundleSection.objects.get_or_create(idx="default", name={"pl": "Default", "en": "Default"})

    def bundle_link_bulk_cleanup_and_create(self, bundle_links: list[BundleLink]):
        BundleLink.objects.filter(product_bundle__shop=self.shop).delete()

        if len(bundle_links) > 0:
            self.logger.set_db_operation("BULK_CREATE", self.name, "BundleLink")
            created_bundle_links = BundleLink.objects.bulk_create(bundle_links, batch_size=self.BULK_BATCH_SIZE)
            self.logger.set_code(None)
            self.logger.info(f"BundleLink created in bulk: {len(bundle_links)}")
            return created_bundle_links

        return None

    def config_link_bulk_cleanup_and_create(self, config_links: list[ConfigurableLink]):
        ConfigurableLink.objects.filter(product_configurable__shop=self.shop).delete()

        if len(config_links) > 0:
            self.logger.set_db_operation("BULK_CREATE", self.name, "ConfigurableLink")
            created_config_links = ConfigurableLink.objects.bulk_create(config_links, batch_size=self.BULK_BATCH_SIZE)
            self.logger.set_code(None)
            self.logger.info(f"ConfigurableLink created in bulk: {len(config_links)}")
            return created_config_links

        return None

    def product_variant_group_bulk_cleanup_and_create(self, group_specs: list[dict]):
        """Full replace of variant groups for the current shop, in a single transaction.

        Each spec is a dict: {"feature": Feature, "name": str | None, "owner": Product | None,
        "members": [(Product, position: int), ...]}. Deleting groups cascades their
        ProductVariantGroupProduct rows, so a single delete clears memberships too.

        The delete + both inserts run inside transaction.atomic() so concurrent readers
        (Matrix product-detail) never observe the gap between delete and re-insert: under
        READ COMMITTED they see the old groups until this transaction commits, then the new
        ones. Without it, a customer hitting the endpoint mid-import would get empty variants.
        """
        with transaction.atomic():
            ProductVariantGroup.objects.filter(shop=self.shop).delete()

            if not group_specs:
                self.logger.info("ProductVariantGroup full replace: 0 groups (cleared)")
                return []

            # uniq_variant_group_shop_owner_feature makes a repeated (owner, feature) spec
            # an IntegrityError that would abort the whole replace after the delete already
            # ran. Collapse duplicates here; first occurrence wins. A NULL owner or feature
            # stays distinct, matching the constraint's nulls_distinct=True.
            unique_specs = []
            seen_axes = set()
            for spec in group_specs:
                owner, feature = spec.get("owner"), spec["feature"]
                axis = (owner.pk, feature.pk) if owner and feature else None
                if axis is not None:
                    if axis in seen_axes:
                        continue
                    seen_axes.add(axis)
                unique_specs.append(spec)

            groups = [
                ProductVariantGroup(
                    shop=self.shop, feature=spec["feature"], name=spec.get("name"), owner=spec.get("owner")
                )
                for spec in unique_specs
            ]
            self.logger.set_db_operation("BULK_CREATE", self.name, "ProductVariantGroup")
            created_groups = ProductVariantGroup.objects.bulk_create(groups, batch_size=self.BULK_BATCH_SIZE)
            self.logger.set_code(None)

            # Magento crosses can list the same SKU twice within one slice; a repeated
            # member would violate unique_together (group, product) and abort the whole
            # replace after the delete already ran. First occurrence wins.
            memberships = []
            for group, spec in zip(created_groups, unique_specs, strict=True):
                seen_products = set()
                for product, position in spec["members"]:
                    if product.pk in seen_products:
                        continue
                    seen_products.add(product.pk)
                    memberships.append(ProductVariantGroupProduct(group=group, product=product, position=position))
            self.logger.set_db_operation("BULK_CREATE", self.name, "ProductVariantGroupProduct")
            ProductVariantGroupProduct.objects.bulk_create(memberships, batch_size=self.BULK_BATCH_SIZE)
            self.logger.set_code(None)
            self.logger.info(
                f"ProductVariantGroup full replace: {len(created_groups)} groups ({len(memberships)} memberships)"
            )

        return created_groups

    def get_feature_set_by_magento_pk(self, magento_pk: int):
        if magento_pk not in self.feature_set_magento_cache:
            self.logger.add_log_param_once("magento_pk", magento_pk)
            self.feature_set_magento_cache[magento_pk] = FeatureSet.objects.get(magento_pk=magento_pk)
        return self.feature_set_magento_cache[magento_pk]

    def get_product_by_magento_pk(self, magento_pk: int) -> Product | None:
        try:
            if magento_pk not in self.products_magento_cache:
                self.products_magento_cache[magento_pk] = Product.objects.get(shop=self.shop, magento_pk=magento_pk)
            return self.products_magento_cache[magento_pk]
        except ObjectDoesNotExist:
            self.logger.set_code(None)
            self.logger.add_log_param_once("magento_pk", magento_pk)
            self.logger.warning(f"Product with magento_pk {magento_pk} not found.")
            return None

    def get_feature_by_magento_pk(self, magento_pk: int) -> Feature | None:
        try:
            if magento_pk not in self.features_magento_cache:
                self.features_magento_cache[magento_pk] = Feature.objects.get(magento_pk=magento_pk)
            return self.features_magento_cache[magento_pk]
        except ObjectDoesNotExist:
            self.logger.set_code(None)
            self.logger.add_log_param_once("magento_pk", magento_pk)
            self.logger.warning(f"Feature with magento_pk {magento_pk} not found.")
            return None

    def get_product_attribute_by_magento_pk(self, product: Product, feature: Feature, attribute_magento_pk: int):
        sku = product.real_product.sku
        try:
            return ProductAttribute.objects.get(
                product=product, feature=feature, attribute__magento_pk=attribute_magento_pk
            )
        except ObjectDoesNotExist:
            self.logger.set_code(None)
            self.logger.add_log_param_once("sku", sku)
            self.logger.add_log_param_once("feature_idx", feature.idx)
            self.logger.add_log_param_once("magento_pk", attribute_magento_pk)
            self.logger.warning(
                f"ProductAttribute for product {product.sku} with magento_pk {attribute_magento_pk} not found."
            )
            return None

    @staticmethod
    def get_skus_with_attribute_exists(feature_idx: str = None) -> set:
        """
        Get all SKUs that have the specified attribute.
        """
        return set(
            ProductAttribute.objects.filter(feature__idx=feature_idx).values_list(
                "product__real_product__sku", flat=True
            )
        )

    def get_skus_with_attribute_exists_in_shop(self, feature: Feature) -> set:
        return set(
            ProductAttribute.objects.filter(feature=feature, product__shop=self.shop).values_list(
                "product__real_product__sku", flat=True
            )
        )

    def delete_product_attributes_by_feature_and_skus(self, feature: Feature, skus: list[str]) -> int:
        qs = ProductAttribute.objects.filter(
            feature=feature, product__shop=self.shop, product__real_product__sku__in=skus
        )
        deleted, _ = qs.delete()
        return deleted

    class ConfigurableLinkHash:
        @staticmethod
        def encode(config_sku: str, subproduct_sku: str, product_attribute_pk: int):
            return f"{config_sku}_{subproduct_sku}_{str(product_attribute_pk)}"

        @staticmethod
        def decode(cl_hash: str):
            return cl_hash.split("_", 2)
