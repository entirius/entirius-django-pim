# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for PIM inheritance API endpoints and service layer.

Covers the three independent inheritance flags introduced to replace the
single `inherits_translations` boolean:
  - inherit_attributes  — all features EXCEPT name/description/short_description
  - inherit_descriptions — name, description, short_description
  - inherit_images       — ProductPicture, ProductVideo, ProductFile
"""

import pytest
from django.contrib.auth import get_user_model
from django.db import models as django_models
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from django_pim.models import (
    Channel,
    FeatureScopeEnum,
    FeatureTypeEnum,
    Files,
    PictureRoleEnum,
    ProductAttribute,
    ProductFile,
    ProductPicture,
    ProductVideo,
    Video,
    VideoRoleEnum,
)
from django_pim.services.inheritance_service import (
    add_product_to_channel,
    copy_translations,
    get_default_product_for,
    materialize_inherited_media,
    materialize_inherited_values,
    propagate_media_to_inheriting,
    propagate_to_inheriting_products,
    toggle_language_override,
    toggle_media_override,
)
from django_pim.settings import DESCRIPTION_FEATURE_IDXS

from .factories import (
    AttributeFactory,
    ChannelFactory,
    CurrencyFactory,
    FeatureFactory,
    FeatureInFeatureSetFactory,
    FeatureSetFactory,
    LanguageFactory,
    ProductFactory,
    RealProductFactory,
)

User = get_user_model()

BASE_URL = "/api/pim/v2/admin"


def _create_test_picture(name="test.png", color="red"):
    """Create a Picture with a real in-memory image file (required by HashedImageField)."""
    import io

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image as PILImage

    from django_pim.services.product_picture_service import upload_picture

    buf = io.BytesIO()
    PILImage.new("RGB", (10, 10), color=color).save(buf, format="PNG")
    buf.seek(0)
    img_file = SimpleUploadedFile(name, buf.read(), content_type="image/png")
    return upload_picture(img_file)


# ============================================================================
# Fixtures — auth
# ============================================================================


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        username="inheritance_admin",
        email="inheritance_admin@test.com",
        password="adminpass123",
        is_staff=True,
        is_superuser=False,
    )


@pytest.fixture
def regular_user(db):
    return User.objects.create_user(
        username="inheritance_regular",
        email="inheritance_regular@test.com",
        password="regularpass123",
        is_staff=False,
        is_superuser=False,
    )


@pytest.fixture
def admin_token(admin_user):
    return str(RefreshToken.for_user(admin_user).access_token)


@pytest.fixture
def regular_token(regular_user):
    return str(RefreshToken.for_user(regular_user).access_token)


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def authenticated_client(api_client, admin_token):
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {admin_token}")
    return api_client


# ============================================================================
# Fixtures — regional data
# ============================================================================


@pytest.fixture
def lang_en(db):
    return LanguageFactory(iso2="EN")


@pytest.fixture
def lang_pl(db):
    return LanguageFactory(iso2="PL")


@pytest.fixture
def lang_de(db):
    return LanguageFactory(iso2="DE")


@pytest.fixture
def currency(db):
    return CurrencyFactory(iso3="EUR")


# ============================================================================
# Fixtures — channels
# ============================================================================


@pytest.fixture
def default_channel(db, lang_en, currency):
    ch = ChannelFactory(idx="default-ch", name="Default Channel", default_language=lang_en, default_currency=currency)
    ch.is_default = True
    ch.inheritance_enabled = True
    ch.save()
    return ch


@pytest.fixture
def secondary_channel(db, lang_en, currency):
    ch = ChannelFactory(
        idx="secondary-ch", name="Secondary Channel", default_language=lang_en, default_currency=currency
    )
    ch.inheritance_enabled = True
    ch.save()
    return ch


# ============================================================================
# Fixtures — features
# ============================================================================


@pytest.fixture
def shared_feature_set(db):
    return FeatureSetFactory(idx="shared-fs", name="Shared FS")


@pytest.fixture
def name_feature(db):
    """DESCRIPTION_FEATURE_IDXS member — governed by inherit_descriptions."""
    return FeatureFactory(idx="name", feature_type=FeatureTypeEnum.VARCHAR255_T9N, scope=FeatureScopeEnum.SYSTEM)


@pytest.fixture
def description_feature(db):
    """DESCRIPTION_FEATURE_IDXS member — governed by inherit_descriptions."""
    return FeatureFactory(idx="description", feature_type=FeatureTypeEnum.TEXT_T9N, scope=FeatureScopeEnum.SYSTEM)


@pytest.fixture
def short_desc_feature(db):
    """DESCRIPTION_FEATURE_IDXS member — governed by inherit_descriptions."""
    return FeatureFactory(idx="short_description", feature_type=FeatureTypeEnum.TEXT_T9N, scope=FeatureScopeEnum.SYSTEM)


@pytest.fixture
def bool_feature(db):
    """Non-description feature — governed by inherit_attributes."""
    return FeatureFactory(idx="test-bool", feature_type=FeatureTypeEnum.BOOL)


@pytest.fixture
def select_attribute_a(db, select_feature):
    return AttributeFactory(feature=select_feature, idx="attr-a")


@pytest.fixture
def select_attribute_b(db, select_feature):
    return AttributeFactory(feature=select_feature, idx="attr-b")


@pytest.fixture
def select_feature(db):
    """SELECT feature — non-description, carries attribute FK."""
    return FeatureFactory(idx="test-select", feature_type=FeatureTypeEnum.SELECT)


@pytest.fixture
def multiselect_feature(db):
    """MULTISELECT feature — multiple ProductAttribute rows per product."""
    return FeatureFactory(idx="test-multiselect", feature_type=FeatureTypeEnum.MULTISELECT)


@pytest.fixture
def multiselect_attr_x(db, multiselect_feature):
    return AttributeFactory(feature=multiselect_feature, idx="ms-x")


@pytest.fixture
def multiselect_attr_y(db, multiselect_feature):
    return AttributeFactory(feature=multiselect_feature, idx="ms-y")


@pytest.fixture
def features_in_set(db, shared_feature_set, name_feature, description_feature, bool_feature):
    FeatureInFeatureSetFactory(feature_set=shared_feature_set, feature=name_feature)
    FeatureInFeatureSetFactory(feature_set=shared_feature_set, feature=description_feature)
    FeatureInFeatureSetFactory(feature_set=shared_feature_set, feature=bool_feature)


# ============================================================================
# Fixtures — products
# ============================================================================


@pytest.fixture
def default_product(
    db, default_channel, shared_feature_set, features_in_set, name_feature, description_feature, bool_feature
):
    rp = RealProductFactory(sku="INHERIT-001")
    product = ProductFactory(shop=default_channel, feature_set=shared_feature_set, real_product=rp)
    ProductAttribute.objects.create(
        product=product, feature=name_feature, value_txt_t9n={"en": "Chair", "pl": "Krzeslo"}
    )
    ProductAttribute.objects.create(
        product=product, feature=description_feature, value_txt_t9n={"en": "A nice chair", "pl": "Ladne krzeslo"}
    )
    ProductAttribute.objects.create(product=product, feature=bool_feature, value_bool=True)
    return product


@pytest.fixture
def inheriting_product(db, secondary_channel, shared_feature_set, features_in_set, default_product):
    """Product on secondary channel with both descriptions and attributes inherited."""
    rp = default_product.real_product
    return ProductFactory(
        shop=secondary_channel,
        feature_set=shared_feature_set,
        real_product=rp,
        inherit_attributes=True,
        inherit_descriptions=True,
    )


# ============================================================================
# Fixtures — media helpers
# ============================================================================


@pytest.fixture
def picture(db):
    return _create_test_picture("test.png", "red")


@pytest.fixture
def video(db):
    return Video.objects.create(title="Test Video", video_url="https://www.youtube.com/watch?v=test123")


@pytest.fixture
def files_obj(db):
    return Files.objects.create(sha1="11223344" * 5, original_file_name="test.pdf")


# ============================================================================
# Channel model tests
# ============================================================================


@pytest.mark.django_db
class TestChannelDefaultBehavior:
    """Channel.is_default field and save/delete constraints."""

    def test_channel_save_atomically_clears_previous_default(self, default_channel, lang_en, currency):
        # Arrange
        ch2 = ChannelFactory(idx="ch2-default", name="Channel 2", default_language=lang_en, default_currency=currency)

        # Act
        ch2.is_default = True
        ch2.save()

        # Assert
        default_channel.refresh_from_db()
        ch2.refresh_from_db()
        assert default_channel.is_default is False
        assert ch2.is_default is True

    def test_delete_default_channel_raises_protected_error(self, default_channel):
        with pytest.raises(django_models.ProtectedError):
            default_channel.delete()

    def test_delete_non_default_channel_succeeds(self, lang_en, currency, default_channel):
        # Arrange
        ch = ChannelFactory(
            idx="non-default-ch", name="Non Default", default_language=lang_en, default_currency=currency
        )

        # Act
        ch.delete()

        # Assert
        assert not Channel.objects.filter(idx="non-default-ch").exists()

    def test_inheritance_enabled_default_false(self, lang_en, currency, default_channel):
        ch = ChannelFactory(idx="fresh-ch", name="Fresh Channel", default_language=lang_en, default_currency=currency)
        assert ch.inheritance_enabled is False

    def test_channel_stores_default_inheritance_flags(self, default_channel):
        default_channel.default_inheritance_flags = ["attributes", "descriptions"]
        default_channel.save()
        default_channel.refresh_from_db()
        assert set(default_channel.default_inheritance_flags) == {"attributes", "descriptions"}

    def test_invalid_inheritance_flag_raises_value_error(self, default_channel):
        default_channel.default_inheritance_flags = ["invalid_flag"]
        with pytest.raises(ValueError, match="Invalid inheritance flags"):
            default_channel.save()


# ============================================================================
# Service: materialize_inherited_values — flag routing
# ============================================================================


@pytest.mark.django_db
class TestMaterializeDescriptionsOnly:
    """inherit_descriptions=True, inherit_attributes=False."""

    def test_copies_description_features_only(
        self,
        default_product,
        secondary_channel,
        shared_feature_set,
        features_in_set,
        name_feature,
        description_feature,
        bool_feature,
    ):
        # Arrange
        rp = default_product.real_product
        product = ProductFactory(
            shop=secondary_channel,
            feature_set=shared_feature_set,
            real_product=rp,
            inherit_descriptions=True,
            inherit_attributes=False,
        )

        # Act
        count = materialize_inherited_values(product)

        # Assert — name + description copied; bool skipped
        assert count == 2
        assert ProductAttribute.objects.filter(product=product, feature=name_feature).exists()
        assert ProductAttribute.objects.filter(product=product, feature=description_feature).exists()
        assert not ProductAttribute.objects.filter(product=product, feature=bool_feature).exists()

    def test_t9n_values_correct(
        self, default_product, secondary_channel, shared_feature_set, features_in_set, name_feature
    ):
        rp = default_product.real_product
        product = ProductFactory(
            shop=secondary_channel,
            feature_set=shared_feature_set,
            real_product=rp,
            inherit_descriptions=True,
            inherit_attributes=False,
        )
        materialize_inherited_values(product)
        attr = ProductAttribute.objects.get(product=product, feature=name_feature)
        assert attr.value_txt_t9n["en"] == "Chair"
        assert attr.value_txt_t9n["pl"] == "Krzeslo"


@pytest.mark.django_db
class TestMaterializeAttributesOnly:
    """inherit_attributes=True, inherit_descriptions=False."""

    def test_copies_non_description_features_only(
        self, default_product, secondary_channel, shared_feature_set, features_in_set, name_feature, bool_feature
    ):
        rp = default_product.real_product
        product = ProductFactory(
            shop=secondary_channel,
            feature_set=shared_feature_set,
            real_product=rp,
            inherit_descriptions=False,
            inherit_attributes=True,
        )
        count = materialize_inherited_values(product)

        # Assert — only bool_feature is a non-description attribute
        assert count == 1
        assert not ProductAttribute.objects.filter(product=product, feature=name_feature).exists()
        assert ProductAttribute.objects.filter(product=product, feature=bool_feature).exists()

    def test_bool_value_correct(
        self, default_product, secondary_channel, shared_feature_set, features_in_set, bool_feature
    ):
        rp = default_product.real_product
        product = ProductFactory(
            shop=secondary_channel,
            feature_set=shared_feature_set,
            real_product=rp,
            inherit_descriptions=False,
            inherit_attributes=True,
        )
        materialize_inherited_values(product)
        attr = ProductAttribute.objects.get(product=product, feature=bool_feature)
        assert attr.value_bool is True


@pytest.mark.django_db
class TestMaterializeBothFlags:
    """inherit_attributes=True AND inherit_descriptions=True."""

    def test_copies_all_features_in_intersection(
        self, inheriting_product, name_feature, description_feature, bool_feature
    ):
        count = materialize_inherited_values(inheriting_product)
        assert count == 3
        for feature in (name_feature, description_feature, bool_feature):
            assert ProductAttribute.objects.filter(product=inheriting_product, feature=feature).exists()

    def test_overridden_langs_initialized_empty(self, inheriting_product, name_feature):
        materialize_inherited_values(inheriting_product)
        attr = ProductAttribute.objects.get(product=inheriting_product, feature=name_feature)
        assert attr.overridden_langs == []


@pytest.mark.django_db
class TestMaterializeNoneSkips:
    """Both flags False — nothing should be copied."""

    def test_returns_zero_when_both_flags_false(
        self, default_product, secondary_channel, shared_feature_set, features_in_set
    ):
        rp = default_product.real_product
        product = ProductFactory(
            shop=secondary_channel,
            feature_set=shared_feature_set,
            real_product=rp,
            inherit_attributes=False,
            inherit_descriptions=False,
        )
        count = materialize_inherited_values(product)
        assert count == 0

    def test_no_attributes_created(self, default_product, secondary_channel, shared_feature_set, features_in_set):
        rp = default_product.real_product
        product = ProductFactory(
            shop=secondary_channel,
            feature_set=shared_feature_set,
            real_product=rp,
            inherit_attributes=False,
            inherit_descriptions=False,
        )
        materialize_inherited_values(product)
        assert not ProductAttribute.objects.filter(product=product).exists()


@pytest.mark.django_db
def test_materialize_respects_channel_disabled(default_product, secondary_channel, shared_feature_set, features_in_set):
    """inheritance_enabled=False on channel blocks materialization entirely."""
    secondary_channel.inheritance_enabled = False
    secondary_channel.save()

    rp = default_product.real_product
    product = ProductFactory(
        shop=secondary_channel,
        feature_set=shared_feature_set,
        real_product=rp,
        inherit_attributes=True,
        inherit_descriptions=True,
    )
    count = materialize_inherited_values(product)
    assert count == 0


# ============================================================================
# Service: SELECT and MULTISELECT bug fixes
# ============================================================================


@pytest.mark.django_db
def test_materialize_select_copies_attribute_fk(
    db, default_channel, secondary_channel, select_feature, select_attribute_a
):
    """SELECT feature must copy the attribute FK, not just leave it None."""
    # Arrange
    fs = FeatureSetFactory(idx="sel-fs")
    FeatureInFeatureSetFactory(feature_set=fs, feature=select_feature)

    rp = RealProductFactory(sku="SEL-001")
    src = ProductFactory(shop=default_channel, feature_set=fs, real_product=rp)
    ProductAttribute.objects.create(product=src, feature=select_feature, attribute=select_attribute_a)

    target = ProductFactory(shop=secondary_channel, feature_set=fs, real_product=rp, inherit_attributes=True)

    # Act
    materialize_inherited_values(target)

    # Assert
    attr = ProductAttribute.objects.get(product=target, feature=select_feature)
    assert attr.attribute is not None
    assert attr.attribute.idx == "attr-a"


@pytest.mark.django_db
def test_materialize_multiselect_creates_multiple_rows(
    db, default_channel, secondary_channel, multiselect_feature, multiselect_attr_x, multiselect_attr_y
):
    """MULTISELECT must create one row per attribute value, not a single row."""
    # Arrange
    fs = FeatureSetFactory(idx="ms-fs")
    FeatureInFeatureSetFactory(feature_set=fs, feature=multiselect_feature)

    rp = RealProductFactory(sku="MS-001")
    src = ProductFactory(shop=default_channel, feature_set=fs, real_product=rp)
    ProductAttribute.objects.create(product=src, feature=multiselect_feature, attribute=multiselect_attr_x)
    ProductAttribute.objects.create(product=src, feature=multiselect_feature, attribute=multiselect_attr_y)

    target = ProductFactory(shop=secondary_channel, feature_set=fs, real_product=rp, inherit_attributes=True)

    # Act
    materialize_inherited_values(target)

    # Assert — two rows, one per attribute
    rows = list(ProductAttribute.objects.filter(product=target, feature=multiselect_feature).order_by("attribute__idx"))
    assert len(rows) == 2
    idx_values = {r.attribute.idx for r in rows}
    assert idx_values == {"ms-x", "ms-y"}


@pytest.mark.django_db
def test_materialize_non_t9n_all_or_nothing(db, default_channel, secondary_channel, bool_feature):
    """Non-t9n feature with overridden_langs=["*"] is not overwritten."""
    fs = FeatureSetFactory(idx="non-t9n-fs")
    FeatureInFeatureSetFactory(feature_set=fs, feature=bool_feature)

    rp = RealProductFactory(sku="NONT9N-001")
    src = ProductFactory(shop=default_channel, feature_set=fs, real_product=rp)
    ProductAttribute.objects.create(product=src, feature=bool_feature, value_bool=True)

    target = ProductFactory(shop=secondary_channel, feature_set=fs, real_product=rp, inherit_attributes=True)
    # Pre-create with all-override marker
    existing = ProductAttribute.objects.create(
        product=target, feature=bool_feature, value_bool=False, overridden_langs=["*"]
    )

    # Act
    materialize_inherited_values(target)

    # Assert — overridden, must not be changed
    existing.refresh_from_db()
    assert existing.value_bool is False


@pytest.mark.django_db
def test_materialize_t9n_respects_overridden_langs(inheriting_product, name_feature):
    """Per-language override is preserved during materialization."""
    # Arrange — "en" is overridden with custom text
    ProductAttribute.objects.create(
        product=inheriting_product, feature=name_feature, value_txt_t9n={"en": "My Override"}, overridden_langs=["en"]
    )

    # Act
    materialize_inherited_values(inheriting_product)

    # Assert
    attr = ProductAttribute.objects.get(product=inheriting_product, feature=name_feature)
    assert attr.value_txt_t9n["en"] == "My Override"  # protected
    assert attr.value_txt_t9n["pl"] == "Krzeslo"  # inherited


@pytest.mark.django_db
def test_materialize_returns_zero_with_no_default_product(secondary_channel, shared_feature_set, features_in_set):
    """Orphan product (no counterpart on default channel) returns 0."""
    rp = RealProductFactory(sku="ORPHAN-001")
    orphan = ProductFactory(
        shop=secondary_channel,
        feature_set=shared_feature_set,
        real_product=rp,
        inherit_attributes=True,
        inherit_descriptions=True,
    )
    assert materialize_inherited_values(orphan) == 0


@pytest.mark.django_db
def test_feature_set_intersection_limits_materialization(
    secondary_channel, default_product, name_feature, features_in_set
):
    """Only features present in both feature sets are materialized."""
    alt_fs = FeatureSetFactory(idx="alt-fs-narrow")
    FeatureInFeatureSetFactory(feature_set=alt_fs, feature=name_feature)

    rp = default_product.real_product
    narrow_product = ProductFactory(
        shop=secondary_channel, feature_set=alt_fs, real_product=rp, inherit_descriptions=True, inherit_attributes=True
    )
    count = materialize_inherited_values(narrow_product)
    assert count == 1
    assert ProductAttribute.objects.filter(product=narrow_product, feature=name_feature).exists()


# ============================================================================
# Service: materialize_inherited_media
# ============================================================================


@pytest.mark.django_db
def test_media_materialize_creates_inherited_picture(db, default_channel, secondary_channel, picture):
    """materialize_inherited_media creates ProductPicture with is_inherited=True."""
    rp = RealProductFactory(sku="MEDIA-001")
    src = ProductFactory(shop=default_channel, real_product=rp)
    ProductPicture.objects.create(product=src, picture=picture, picture_role=PictureRoleEnum.GENERAL, position=1)

    target = ProductFactory(shop=secondary_channel, real_product=rp, inherit_images=True)
    count = materialize_inherited_media(target)

    assert count == 1
    pp = ProductPicture.objects.get(product=target)
    assert pp.is_inherited is True
    assert pp.picture_id == picture.pk


@pytest.mark.django_db
def test_media_materialize_preserves_local_pictures(db, default_channel, secondary_channel, picture):
    """Local (is_inherited=False) pictures are not removed during materialization."""
    rp = RealProductFactory(sku="MEDIA-002")
    src = ProductFactory(shop=default_channel, real_product=rp)
    ProductPicture.objects.create(product=src, picture=picture, picture_role=PictureRoleEnum.GENERAL, position=1)

    target = ProductFactory(shop=secondary_channel, real_product=rp, inherit_images=True)
    local_pic = _create_test_picture("local.png", "blue")
    local_pp = ProductPicture.objects.create(
        product=target, picture=local_pic, picture_role=PictureRoleEnum.GENERAL, position=99, is_inherited=False
    )

    materialize_inherited_media(target)

    # Local must still exist
    local_pp.refresh_from_db()
    assert local_pp.is_inherited is False


@pytest.mark.django_db
def test_media_materialize_deletes_old_inherited_before_refresh(db, default_channel, secondary_channel, picture):
    """Old inherited pictures are replaced on re-materialization."""
    rp = RealProductFactory(sku="MEDIA-003")
    src = ProductFactory(shop=default_channel, real_product=rp)
    ProductPicture.objects.create(product=src, picture=picture, picture_role=PictureRoleEnum.GENERAL, position=1)

    target = ProductFactory(shop=secondary_channel, real_product=rp, inherit_images=True)
    # First materialization
    materialize_inherited_media(target)
    assert ProductPicture.objects.filter(product=target, is_inherited=True).count() == 1

    # Second materialization — must not double up
    materialize_inherited_media(target)
    assert ProductPicture.objects.filter(product=target, is_inherited=True).count() == 1


@pytest.mark.django_db
def test_media_materialize_skips_when_flag_false(db, default_channel, secondary_channel, picture):
    """inherit_images=False prevents any media copy."""
    rp = RealProductFactory(sku="MEDIA-004")
    src = ProductFactory(shop=default_channel, real_product=rp)
    ProductPicture.objects.create(product=src, picture=picture, picture_role=PictureRoleEnum.GENERAL, position=1)

    target = ProductFactory(shop=secondary_channel, real_product=rp, inherit_images=False)
    count = materialize_inherited_media(target)
    assert count == 0
    assert not ProductPicture.objects.filter(product=target).exists()


@pytest.mark.django_db
def test_media_materialize_copies_video(db, default_channel, secondary_channel, video):
    """Videos are copied with is_inherited=True."""
    rp = RealProductFactory(sku="VID-001")
    src = ProductFactory(shop=default_channel, real_product=rp)
    ProductVideo.objects.create(product=src, video=video, video_role=VideoRoleEnum.MAIN, position=0)

    target = ProductFactory(shop=secondary_channel, real_product=rp, inherit_images=True)
    count = materialize_inherited_media(target)
    assert count == 1
    pv = ProductVideo.objects.get(product=target)
    assert pv.is_inherited is True


@pytest.mark.django_db
def test_media_materialize_copies_file(db, default_channel, secondary_channel, files_obj):
    """Files are copied with is_inherited=True."""
    rp = RealProductFactory(sku="FILE-001")
    src = ProductFactory(shop=default_channel, real_product=rp)
    ProductFile.objects.create(product=src, file=files_obj)

    target = ProductFactory(shop=secondary_channel, real_product=rp, inherit_images=True)
    count = materialize_inherited_media(target)
    assert count == 1
    pf = ProductFile.objects.get(product=target)
    assert pf.is_inherited is True


# ============================================================================
# Service: propagate_to_inheriting_products
# ============================================================================


@pytest.mark.django_db
class TestPropagateAttributes:
    """propagate_to_inheriting_products pushes attribute changes downstream."""

    def test_propagate_updates_inheriting_product(self, default_product, inheriting_product, name_feature):
        # Arrange
        materialize_inherited_values(inheriting_product)
        default_attr = ProductAttribute.objects.get(product=default_product, feature=name_feature)
        default_attr.value_txt_t9n = {"en": "Updated Chair", "pl": "Zaktualizowane krzeslo"}
        default_attr.save()

        # Act
        count = propagate_to_inheriting_products(default_product)

        # Assert
        assert count == 1
        updated = ProductAttribute.objects.get(product=inheriting_product, feature=name_feature)
        assert updated.value_txt_t9n["en"] == "Updated Chair"

    def test_propagate_skips_overridden_lang(self, default_product, inheriting_product, name_feature):
        # Arrange
        materialize_inherited_values(inheriting_product)
        attr = ProductAttribute.objects.get(product=inheriting_product, feature=name_feature)
        attr.overridden_langs = ["en"]
        attr.value_txt_t9n = {"en": "My Override", "pl": "Krzeslo"}
        attr.save()

        default_attr = ProductAttribute.objects.get(product=default_product, feature=name_feature)
        default_attr.value_txt_t9n = {"en": "New Default", "pl": "Nowy domyslny"}
        default_attr.save()

        # Act
        propagate_to_inheriting_products(default_product)

        # Assert
        attr.refresh_from_db()
        assert attr.value_txt_t9n["en"] == "My Override"  # protected
        assert attr.value_txt_t9n["pl"] == "Nowy domyslny"  # inherited

    def test_propagate_only_affects_inheriting_products(
        self, secondary_channel, shared_feature_set, features_in_set, default_product
    ):
        # Arrange — non-inheriting product, same channel
        rp = RealProductFactory(sku="NOINHERIT-001")
        ProductFactory(
            shop=secondary_channel,
            feature_set=shared_feature_set,
            real_product=rp,
            inherit_attributes=False,
            inherit_descriptions=False,
        )
        count = propagate_to_inheriting_products(default_product)
        assert count == 0

    def test_propagate_returns_count_of_updated_products(self, default_product, inheriting_product):
        materialize_inherited_values(inheriting_product)
        count = propagate_to_inheriting_products(default_product)
        assert count == 1


@pytest.mark.django_db
def test_propagate_images(db, default_channel, secondary_channel, picture):
    """propagate_media_to_inheriting copies media to inherit_images products."""
    rp = RealProductFactory(sku="PROPIMG-001")
    src = ProductFactory(shop=default_channel, real_product=rp)
    ProductPicture.objects.create(product=src, picture=picture, picture_role=PictureRoleEnum.GENERAL, position=1)

    target = ProductFactory(shop=secondary_channel, real_product=rp, inherit_images=True)
    count = propagate_media_to_inheriting(src)

    assert count == 1
    assert ProductPicture.objects.filter(product=target, is_inherited=True).exists()


@pytest.mark.django_db
def test_propagate_mixed_flags_across_products(
    db, default_channel, secondary_channel, shared_feature_set, features_in_set, bool_feature, picture
):
    """propagate_to_inheriting_products handles inherit_attributes + inherit_images on same product."""
    rp = RealProductFactory(sku="MIXED-001")
    src = ProductFactory(shop=default_channel, feature_set=shared_feature_set, real_product=rp)
    ProductAttribute.objects.create(product=src, feature=bool_feature, value_bool=True)
    ProductPicture.objects.create(product=src, picture=picture, picture_role=PictureRoleEnum.GENERAL, position=1)

    target = ProductFactory(
        shop=secondary_channel,
        feature_set=shared_feature_set,
        real_product=rp,
        inherit_attributes=True,
        inherit_images=True,
    )

    propagate_to_inheriting_products(src)

    assert ProductAttribute.objects.filter(product=target, feature=bool_feature).exists()
    assert ProductPicture.objects.filter(product=target, is_inherited=True).exists()


# ============================================================================
# Service: add_product_to_channel
# ============================================================================


@pytest.mark.django_db
class TestAddProductToChannel:
    """add_product_to_channel creates a channel copy of a product."""

    def test_creates_product_in_target_channel(self, default_product, secondary_channel):
        new_prod = add_product_to_channel(
            default_product, "secondary-ch", inherit_attributes=True, inherit_descriptions=True
        )
        assert new_prod.shop.idx == "secondary-ch"
        assert new_prod.real_product == default_product.real_product
        assert new_prod.inherit_attributes is True
        assert new_prod.inherit_descriptions is True

    def test_add_with_partial_flags(self, default_product, secondary_channel):
        new_prod = add_product_to_channel(
            default_product, "secondary-ch", inherit_attributes=False, inherit_descriptions=True, inherit_images=False
        )
        assert new_prod.inherit_attributes is False
        assert new_prod.inherit_descriptions is True
        assert new_prod.inherit_images is False

    def test_add_defaults_no_inherit(self, default_product, secondary_channel):
        new_prod = add_product_to_channel(default_product, "secondary-ch")
        assert new_prod.inherit_attributes is False
        assert new_prod.inherit_descriptions is False
        assert new_prod.inherit_images is False

    def test_copy_content_mode_copies_attribute_values(
        self, default_product, secondary_channel, name_feature, features_in_set
    ):
        new_prod = add_product_to_channel(default_product, "secondary-ch", copy_content=True)
        attr = ProductAttribute.objects.get(product=new_prod, feature=name_feature)
        assert attr.value_txt_t9n["en"] == "Chair"

    def test_raises_value_error_if_product_already_exists(
        self, default_product, secondary_channel, shared_feature_set, features_in_set
    ):
        ProductFactory(
            shop=secondary_channel, feature_set=shared_feature_set, real_product=default_product.real_product
        )
        with pytest.raises(ValueError, match="already exists"):
            add_product_to_channel(default_product, "secondary-ch")

    def test_raises_channel_does_not_exist(self, default_product):
        with pytest.raises(Channel.DoesNotExist):
            add_product_to_channel(default_product, "nonexistent-channel-idx")

    def test_add_with_inherit_images_materializes_media(self, db, default_channel, secondary_channel, picture):
        rp = RealProductFactory(sku="ADDMEDIA-001")
        src = ProductFactory(shop=default_channel, real_product=rp)
        ProductPicture.objects.create(product=src, picture=picture, picture_role=PictureRoleEnum.GENERAL, position=1)
        new_prod = add_product_to_channel(src, "secondary-ch", inherit_images=True)
        assert ProductPicture.objects.filter(product=new_prod, is_inherited=True).exists()


# ============================================================================
# Service: toggle_language_override
# ============================================================================


@pytest.mark.django_db
class TestToggleLanguageOverride:
    """toggle_language_override marks/unmarks per-language overrides."""

    def test_toggle_on_adds_language_to_overridden(self, inheriting_product, name_feature):
        materialize_inherited_values(inheriting_product)
        toggle_language_override(inheriting_product, "name", "en", override=True)
        attr = ProductAttribute.objects.get(product=inheriting_product, feature=name_feature)
        assert "en" in attr.overridden_langs

    def test_toggle_off_removes_language_and_rematerializes(self, inheriting_product, default_product, name_feature):
        # Arrange
        materialize_inherited_values(inheriting_product)
        attr = ProductAttribute.objects.get(product=inheriting_product, feature=name_feature)
        attr.overridden_langs = ["en"]
        attr.value_txt_t9n = {"en": "Custom Value", "pl": "Krzeslo"}
        attr.save()

        # Act
        toggle_language_override(inheriting_product, "name", "en", override=False)

        # Assert — "en" re-materialized from default
        attr.refresh_from_db()
        assert "en" not in attr.overridden_langs
        assert attr.value_txt_t9n["en"] == "Chair"

    def test_raises_when_attribute_not_found(self, inheriting_product):
        # No ProductAttribute for name feature yet
        with pytest.raises(ValueError):
            toggle_language_override(inheriting_product, "name", "en", override=True)

    def test_raises_when_description_inheritance_not_enabled(self, inheriting_product, name_feature):
        """name is a description feature — needs inherit_descriptions=True."""
        materialize_inherited_values(inheriting_product)
        inheriting_product.inherit_descriptions = False
        inheriting_product.save()
        with pytest.raises(ValueError, match="Description inheritance is not enabled"):
            toggle_language_override(inheriting_product, "name", "en", override=True)

    def test_raises_when_attribute_inheritance_not_enabled(self, db, default_channel, secondary_channel, bool_feature):
        """Non-description feature (bool) needs inherit_attributes=True."""
        fs = FeatureSetFactory(idx="tog-fs")
        FeatureInFeatureSetFactory(feature_set=fs, feature=bool_feature)

        rp = RealProductFactory(sku="TOG-001")
        src = ProductFactory(shop=default_channel, feature_set=fs, real_product=rp)
        ProductAttribute.objects.create(product=src, feature=bool_feature, value_bool=True)

        target = ProductFactory(shop=secondary_channel, feature_set=fs, real_product=rp, inherit_attributes=False)
        materialize_inherited_values(target)

        with pytest.raises(ValueError, match="Attribute inheritance is not enabled"):
            toggle_language_override(target, "test-bool", "en", override=True)

    def test_toggle_override_for_description_feature_uses_correct_flag(self, inheriting_product, description_feature):
        """description is a DESCRIPTION_FEATURE_IDXS member — checks inherit_descriptions."""
        materialize_inherited_values(inheriting_product)
        # inherit_descriptions=True, so toggle must work
        toggle_language_override(inheriting_product, "description", "en", override=True)
        attr = ProductAttribute.objects.get(product=inheriting_product, feature=description_feature)
        assert "en" in attr.overridden_langs

    def test_toggle_override_for_attribute_feature_uses_correct_flag(self, inheriting_product, bool_feature):
        """bool is NOT in DESCRIPTION_FEATURE_IDXS — checks inherit_attributes."""
        materialize_inherited_values(inheriting_product)
        # inherit_attributes=True on inheriting_product fixture
        toggle_language_override(inheriting_product, "test-bool", "en", override=True)
        attr = ProductAttribute.objects.get(product=inheriting_product, feature=bool_feature)
        assert "en" in attr.overridden_langs


# ============================================================================
# Service: toggle_media_override
# ============================================================================


@pytest.mark.django_db
class TestToggleMediaOverride:
    """toggle_media_override marks a media item local or inherited."""

    def test_toggle_picture_override_marks_local(self, db, default_channel, secondary_channel, picture):
        rp = RealProductFactory(sku="TMOV-001")
        src = ProductFactory(shop=default_channel, real_product=rp)
        ProductPicture.objects.create(product=src, picture=picture, picture_role=PictureRoleEnum.GENERAL, position=1)
        target = ProductFactory(shop=secondary_channel, real_product=rp, inherit_images=True)
        materialize_inherited_media(target)

        pp = ProductPicture.objects.get(product=target)
        toggle_media_override(target, picture_id=pp.pk, override=True)
        pp.refresh_from_db()
        assert pp.is_inherited is False

    def test_toggle_picture_override_marks_inherited(self, db, default_channel, secondary_channel, picture):
        rp = RealProductFactory(sku="TMOV-002")
        src = ProductFactory(shop=default_channel, real_product=rp)
        ProductPicture.objects.create(product=src, picture=picture, picture_role=PictureRoleEnum.GENERAL, position=1)
        target = ProductFactory(shop=secondary_channel, real_product=rp, inherit_images=True)
        materialize_inherited_media(target)

        pp = ProductPicture.objects.get(product=target)
        # First mark local
        toggle_media_override(target, picture_id=pp.pk, override=True)
        # Then revert to inherited
        toggle_media_override(target, picture_id=pp.pk, override=False)
        pp.refresh_from_db()
        assert pp.is_inherited is True

    def test_toggle_video_override(self, db, default_channel, secondary_channel, video):
        rp = RealProductFactory(sku="TVID-001")
        src = ProductFactory(shop=default_channel, real_product=rp)
        ProductVideo.objects.create(product=src, video=video, video_role=VideoRoleEnum.MAIN, position=0)
        target = ProductFactory(shop=secondary_channel, real_product=rp, inherit_images=True)
        materialize_inherited_media(target)

        pv = ProductVideo.objects.get(product=target)
        toggle_media_override(target, video_id=pv.pk, override=True)
        pv.refresh_from_db()
        assert pv.is_inherited is False

    def test_toggle_file_override(self, db, default_channel, secondary_channel, files_obj):
        rp = RealProductFactory(sku="TFIL-001")
        src = ProductFactory(shop=default_channel, real_product=rp)
        ProductFile.objects.create(product=src, file=files_obj)
        target = ProductFactory(shop=secondary_channel, real_product=rp, inherit_images=True)
        materialize_inherited_media(target)

        pf = ProductFile.objects.get(product=target)
        toggle_media_override(target, file_id=pf.pk, override=True)
        pf.refresh_from_db()
        assert pf.is_inherited is False

    def test_raises_when_inherit_images_false(self, db, secondary_channel, picture):
        rp = RealProductFactory(sku="TMOV-ERR")
        target = ProductFactory(shop=secondary_channel, real_product=rp, inherit_images=False)
        pp = ProductPicture.objects.create(
            product=target, picture=picture, picture_role=PictureRoleEnum.GENERAL, position=1
        )
        with pytest.raises(ValueError, match="Image inheritance is not enabled"):
            toggle_media_override(target, picture_id=pp.pk, override=True)

    def test_raises_when_picture_not_on_product(self, db, secondary_channel):
        rp = RealProductFactory(sku="TMOV-NOTFOUND")
        target = ProductFactory(shop=secondary_channel, real_product=rp, inherit_images=True)
        with pytest.raises(ValueError, match="Picture"):
            toggle_media_override(target, picture_id=99999, override=True)


# ============================================================================
# Service: get_default_product_for
# ============================================================================


@pytest.mark.django_db
class TestGetDefaultProductFor:
    """get_default_product_for locates the default channel counterpart."""

    def test_returns_default_channel_product(self, inheriting_product, default_product):
        result = get_default_product_for(inheriting_product)
        assert result is not None
        assert result.pk == default_product.pk

    def test_returns_none_when_product_is_on_default_channel(self, default_product):
        assert get_default_product_for(default_product) is None

    def test_returns_none_when_no_default_product_exists(self, secondary_channel, shared_feature_set, features_in_set):
        rp = RealProductFactory(sku="NODEFAULT-001")
        product = ProductFactory(shop=secondary_channel, feature_set=shared_feature_set, real_product=rp)
        assert get_default_product_for(product) is None


# ============================================================================
# Service: copy_translations
# ============================================================================


@pytest.mark.django_db
class TestCopyTranslations:
    """copy_translations one-time copies and marks langs as overridden."""

    def test_copy_all_languages_from_source(
        self, default_product, secondary_channel, shared_feature_set, features_in_set, name_feature
    ):
        target = ProductFactory(
            shop=secondary_channel, feature_set=shared_feature_set, real_product=default_product.real_product
        )
        count = copy_translations(default_product, target)
        assert count == 3
        attr = ProductAttribute.objects.get(product=target, feature=name_feature)
        assert attr.value_txt_t9n["en"] == "Chair"
        assert attr.value_txt_t9n["pl"] == "Krzeslo"

    def test_copy_marks_copied_languages_as_overridden(
        self, default_product, secondary_channel, shared_feature_set, features_in_set, name_feature
    ):
        target = ProductFactory(
            shop=secondary_channel, feature_set=shared_feature_set, real_product=default_product.real_product
        )
        copy_translations(default_product, target)
        attr = ProductAttribute.objects.get(product=target, feature=name_feature)
        assert set(attr.overridden_langs) == {"en", "pl"}

    def test_copy_specific_language_only(
        self, default_product, secondary_channel, shared_feature_set, features_in_set, name_feature
    ):
        target = ProductFactory(
            shop=secondary_channel, feature_set=shared_feature_set, real_product=default_product.real_product
        )
        copy_translations(default_product, target, languages=["en"])
        attr = ProductAttribute.objects.get(product=target, feature=name_feature)
        assert attr.value_txt_t9n.get("en") == "Chair"
        assert "pl" not in (attr.value_txt_t9n or {})
        assert "en" in attr.overridden_langs
        assert "pl" not in attr.overridden_langs


# ============================================================================
# API integration tests
# ============================================================================


@pytest.mark.django_db
class TestPatchInheritanceFlags:
    """PATCH product updates inherit_* flags and returns them in response."""

    def test_enable_inherit_descriptions_via_patch_materializes_values(
        self,
        authenticated_client,
        default_product,
        secondary_channel,
        shared_feature_set,
        features_in_set,
        name_feature,
    ):
        # Arrange — product exists on secondary, no inheritance yet
        rp = default_product.real_product
        secondary_prod = ProductFactory(
            shop=secondary_channel,
            feature_set=shared_feature_set,
            real_product=rp,
            inherit_descriptions=False,
            inherit_attributes=False,
        )

        # Act
        response = authenticated_client.patch(
            f"{BASE_URL}/secondary-ch/products/INHERIT-001/", {"inherit_descriptions": True}, format="json"
        )

        # Assert
        assert response.status_code == 200
        assert response.data["inherit_descriptions"] is True
        attr = ProductAttribute.objects.filter(product=secondary_prod, feature=name_feature)
        assert attr.exists()

    def test_patch_response_contains_all_three_flags(self, authenticated_client, inheriting_product, features_in_set):
        response = authenticated_client.patch(
            f"{BASE_URL}/secondary-ch/products/INHERIT-001/", {"inherit_attributes": False}, format="json"
        )
        assert response.status_code == 200
        data = response.data
        assert "inherit_attributes" in data
        assert "inherit_descriptions" in data
        assert "inherit_images" in data


@pytest.mark.django_db
class TestCopyAttributesEndpoint:
    """POST /{channel_idx}/products/{sku}/copy-attributes/ (and alias copy-translations/)."""

    def test_copy_attributes_returns_200(
        self, authenticated_client, default_product, secondary_channel, shared_feature_set, features_in_set
    ):
        ProductFactory(
            shop=secondary_channel, feature_set=shared_feature_set, real_product=default_product.real_product
        )
        response = authenticated_client.post(
            f"{BASE_URL}/secondary-ch/products/INHERIT-001/copy-attributes/",
            {"source_channel_idx": "default-ch"},
            format="json",
        )
        assert response.status_code == 200

    def test_copy_attributes_alias_copy_translations_returns_200(
        self, authenticated_client, default_product, secondary_channel, shared_feature_set, features_in_set
    ):
        """Backward-compatible alias endpoint must work."""
        ProductFactory(
            shop=secondary_channel, feature_set=shared_feature_set, real_product=default_product.real_product
        )
        response = authenticated_client.post(
            f"{BASE_URL}/secondary-ch/products/INHERIT-001/copy-translations/",
            {"source_channel_idx": "default-ch"},
            format="json",
        )
        assert response.status_code == 200

    def test_same_channel_returns_400(self, authenticated_client, default_product):
        response = authenticated_client.post(
            f"{BASE_URL}/default-ch/products/INHERIT-001/copy-attributes/",
            {"source_channel_idx": "default-ch"},
            format="json",
        )
        assert response.status_code == 400

    def test_requires_auth(self, api_client, default_product, secondary_channel, shared_feature_set, features_in_set):
        ProductFactory(
            shop=secondary_channel, feature_set=shared_feature_set, real_product=default_product.real_product
        )
        response = api_client.post(
            f"{BASE_URL}/secondary-ch/products/INHERIT-001/copy-attributes/",
            {"source_channel_idx": "default-ch"},
            format="json",
        )
        assert response.status_code == 401

    def test_requires_admin(
        self, api_client, regular_token, default_product, secondary_channel, shared_feature_set, features_in_set
    ):
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {regular_token}")
        ProductFactory(
            shop=secondary_channel, feature_set=shared_feature_set, real_product=default_product.real_product
        )
        response = api_client.post(
            f"{BASE_URL}/secondary-ch/products/INHERIT-001/copy-attributes/",
            {"source_channel_idx": "default-ch"},
            format="json",
        )
        assert response.status_code == 403


@pytest.mark.django_db
class TestAddToChannelEndpoint:
    """POST /{channel_idx}/products/{sku}/add-to-channel/"""

    def test_returns_201(self, authenticated_client, default_product, secondary_channel):
        response = authenticated_client.post(
            f"{BASE_URL}/default-ch/products/INHERIT-001/add-to-channel/",
            {"target_channel_idx": "secondary-ch", "inherit_attributes": True, "inherit_descriptions": True},
            format="json",
        )
        assert response.status_code == 201

    def test_response_contains_sku(self, authenticated_client, default_product, secondary_channel):
        response = authenticated_client.post(
            f"{BASE_URL}/default-ch/products/INHERIT-001/add-to-channel/",
            {"target_channel_idx": "secondary-ch"},
            format="json",
        )
        assert response.data["sku"] == "INHERIT-001"

    def test_response_reflects_inherit_flags(self, authenticated_client, default_product, secondary_channel):
        response = authenticated_client.post(
            f"{BASE_URL}/default-ch/products/INHERIT-001/add-to-channel/",
            {
                "target_channel_idx": "secondary-ch",
                "inherit_attributes": True,
                "inherit_descriptions": False,
                "inherit_images": True,
            },
            format="json",
        )
        assert response.status_code == 201
        assert response.data["inherit_attributes"] is True
        assert response.data["inherit_descriptions"] is False
        assert response.data["inherit_images"] is True

    def test_duplicate_returns_409(
        self, authenticated_client, default_product, secondary_channel, shared_feature_set, features_in_set
    ):
        ProductFactory(
            shop=secondary_channel, feature_set=shared_feature_set, real_product=default_product.real_product
        )
        response = authenticated_client.post(
            f"{BASE_URL}/default-ch/products/INHERIT-001/add-to-channel/",
            {"target_channel_idx": "secondary-ch"},
            format="json",
        )
        assert response.status_code == 409

    def test_requires_auth(self, api_client, default_product, secondary_channel):
        response = api_client.post(
            f"{BASE_URL}/default-ch/products/INHERIT-001/add-to-channel/",
            {"target_channel_idx": "secondary-ch"},
            format="json",
        )
        assert response.status_code == 401

    def test_requires_admin(self, api_client, regular_token, default_product, secondary_channel):
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {regular_token}")
        response = api_client.post(
            f"{BASE_URL}/default-ch/products/INHERIT-001/add-to-channel/",
            {"target_channel_idx": "secondary-ch"},
            format="json",
        )
        assert response.status_code == 403


@pytest.mark.django_db
class TestToggleOverrideEndpoint:
    """POST /{channel_idx}/products/{sku}/toggle-override/"""

    def test_returns_200(self, authenticated_client, inheriting_product, features_in_set):
        materialize_inherited_values(inheriting_product)
        response = authenticated_client.post(
            f"{BASE_URL}/secondary-ch/products/INHERIT-001/toggle-override/",
            {"feature_idx": "name", "language": "en", "override": True},
            format="json",
        )
        assert response.status_code == 200

    def test_requires_auth(self, api_client, inheriting_product, features_in_set):
        materialize_inherited_values(inheriting_product)
        response = api_client.post(
            f"{BASE_URL}/secondary-ch/products/INHERIT-001/toggle-override/",
            {"feature_idx": "name", "language": "en", "override": True},
            format="json",
        )
        assert response.status_code == 401

    def test_requires_admin(self, api_client, regular_token, inheriting_product, features_in_set):
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {regular_token}")
        materialize_inherited_values(inheriting_product)
        response = api_client.post(
            f"{BASE_URL}/secondary-ch/products/INHERIT-001/toggle-override/",
            {"feature_idx": "name", "language": "en", "override": True},
            format="json",
        )
        assert response.status_code == 403


@pytest.mark.django_db
class TestToggleMediaOverrideEndpoint:
    """POST /{channel_idx}/products/{sku}/toggle-media-override/"""

    def test_returns_200(self, authenticated_client, default_product, secondary_channel, picture):
        # Arrange — inherit images product with a materialized picture
        rp = default_product.real_product
        ProductPicture.objects.create(
            product=default_product, picture=picture, picture_role=PictureRoleEnum.GENERAL, position=1
        )
        target = ProductFactory(shop=secondary_channel, real_product=rp, inherit_images=True)
        materialize_inherited_media(target)
        pp = ProductPicture.objects.get(product=target, is_inherited=True)

        response = authenticated_client.post(
            f"{BASE_URL}/secondary-ch/products/INHERIT-001/toggle-media-override/",
            {"picture_id": pp.pk, "override": True},
            format="json",
        )
        assert response.status_code == 200

    def test_requires_auth(self, api_client, default_product, secondary_channel):
        response = api_client.post(
            f"{BASE_URL}/secondary-ch/products/INHERIT-001/toggle-media-override/",
            {"picture_id": 1, "override": True},
            format="json",
        )
        assert response.status_code == 401

    def test_requires_admin(self, api_client, regular_token, default_product, secondary_channel):
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {regular_token}")
        response = api_client.post(
            f"{BASE_URL}/secondary-ch/products/INHERIT-001/toggle-media-override/",
            {"picture_id": 1, "override": True},
            format="json",
        )
        assert response.status_code == 403


@pytest.mark.django_db
class TestProductDetailInheritanceFields:
    """Product detail response includes the three new flags."""

    def test_detail_contains_inherit_attributes(self, authenticated_client, inheriting_product, features_in_set):
        materialize_inherited_values(inheriting_product)
        response = authenticated_client.get(f"{BASE_URL}/secondary-ch/products/INHERIT-001/")
        assert response.status_code == 200
        assert "inherit_attributes" in response.data
        assert "inherit_descriptions" in response.data
        assert "inherit_images" in response.data

    def test_detail_flags_reflect_product_values(self, authenticated_client, inheriting_product, features_in_set):
        materialize_inherited_values(inheriting_product)
        response = authenticated_client.get(f"{BASE_URL}/secondary-ch/products/INHERIT-001/")
        assert response.data["inherit_attributes"] is True
        assert response.data["inherit_descriptions"] is True
        assert response.data["inherit_images"] is False

    def test_detail_includes_default_channel_idx(self, authenticated_client, inheriting_product, features_in_set):
        materialize_inherited_values(inheriting_product)
        response = authenticated_client.get(f"{BASE_URL}/secondary-ch/products/INHERIT-001/")
        assert response.data["default_channel_idx"] == "default-ch"

    def test_detail_attributes_contain_overridden_langs(
        self, authenticated_client, inheriting_product, features_in_set
    ):
        materialize_inherited_values(inheriting_product)
        response = authenticated_client.get(f"{BASE_URL}/secondary-ch/products/INHERIT-001/")
        assert response.status_code == 200
        attributes = response.data.get("attributes", [])
        if attributes:
            assert "overridden_langs" in attributes[0]


# ============================================================================
# Edge cases
# ============================================================================


@pytest.mark.django_db
def test_default_channel_ignores_inheritance_flags(default_product):
    """Product on the default channel: get_default_product_for returns None."""
    assert get_default_product_for(default_product) is None


@pytest.mark.django_db
def test_description_feature_categorization():
    """DESCRIPTION_FEATURE_IDXS must contain exactly the three system idxs."""
    assert "name" in DESCRIPTION_FEATURE_IDXS
    assert "description" in DESCRIPTION_FEATURE_IDXS
    assert "short_description" in DESCRIPTION_FEATURE_IDXS
    assert "test-bool" not in DESCRIPTION_FEATURE_IDXS
    assert "url_key" not in DESCRIPTION_FEATURE_IDXS


# ============================================================================
# Service: exclude_from_inheritance flag
# ============================================================================


@pytest.mark.django_db
class TestExcludeFromInheritance:
    """Features with exclude_from_inheritance=True are skipped during materialization."""

    def test_materialize_skips_excluded_feature(
        self, default_channel, secondary_channel, shared_feature_set, name_feature, description_feature
    ):
        """Feature with exclude_from_inheritance=True is not copied."""
        # Arrange — mark bool feature as excluded
        excluded_feature = FeatureFactory(
            idx="excluded-feat", feature_type=FeatureTypeEnum.BOOL, exclude_from_inheritance=True
        )
        FeatureInFeatureSetFactory(feature_set=shared_feature_set, feature=name_feature)
        FeatureInFeatureSetFactory(feature_set=shared_feature_set, feature=description_feature)
        FeatureInFeatureSetFactory(feature_set=shared_feature_set, feature=excluded_feature)

        rp = RealProductFactory(sku="EXCL-001")
        default_prod = ProductFactory(shop=default_channel, feature_set=shared_feature_set, real_product=rp)
        ProductAttribute.objects.create(
            product=default_prod, feature=name_feature, value_txt_t9n={"en": "Excluded Test"}
        )
        ProductAttribute.objects.create(product=default_prod, feature=excluded_feature, value_bool=True)

        target = ProductFactory(
            shop=secondary_channel,
            feature_set=shared_feature_set,
            real_product=rp,
            inherit_attributes=True,
            inherit_descriptions=True,
        )

        # Act
        materialize_inherited_values(target)

        # Assert — excluded feature not materialized
        assert not ProductAttribute.objects.filter(product=target, feature=excluded_feature).exists()
        # Non-excluded feature IS materialized
        assert ProductAttribute.objects.filter(product=target, feature=name_feature).exists()

    def test_materialize_includes_non_excluded_feature(
        self, default_channel, secondary_channel, shared_feature_set, name_feature, description_feature
    ):
        """Feature with exclude_from_inheritance=False is copied (regression)."""
        non_excluded = FeatureFactory(
            idx="non-excluded-feat", feature_type=FeatureTypeEnum.BOOL, exclude_from_inheritance=False
        )
        FeatureInFeatureSetFactory(feature_set=shared_feature_set, feature=name_feature)
        FeatureInFeatureSetFactory(feature_set=shared_feature_set, feature=description_feature)
        FeatureInFeatureSetFactory(feature_set=shared_feature_set, feature=non_excluded)

        rp = RealProductFactory(sku="NONEXCL-001")
        default_prod = ProductFactory(shop=default_channel, feature_set=shared_feature_set, real_product=rp)
        ProductAttribute.objects.create(product=default_prod, feature=non_excluded, value_bool=True)

        target = ProductFactory(
            shop=secondary_channel,
            feature_set=shared_feature_set,
            real_product=rp,
            inherit_attributes=True,
            inherit_descriptions=True,
        )

        # Act
        materialize_inherited_values(target)

        # Assert — non-excluded feature IS materialized
        attr = ProductAttribute.objects.filter(product=target, feature=non_excluded).first()
        assert attr is not None
        assert attr.value_bool is True

    def test_propagate_skips_excluded_feature(
        self, default_channel, secondary_channel, shared_feature_set, name_feature, description_feature
    ):
        """Propagation respects exclude_from_inheritance flag."""
        excluded_feature = FeatureFactory(
            idx="prop-excluded", feature_type=FeatureTypeEnum.BOOL, exclude_from_inheritance=True
        )
        FeatureInFeatureSetFactory(feature_set=shared_feature_set, feature=name_feature)
        FeatureInFeatureSetFactory(feature_set=shared_feature_set, feature=description_feature)
        FeatureInFeatureSetFactory(feature_set=shared_feature_set, feature=excluded_feature)

        rp = RealProductFactory(sku="PROPEXCL-001")
        default_prod = ProductFactory(shop=default_channel, feature_set=shared_feature_set, real_product=rp)
        ProductAttribute.objects.create(
            product=default_prod, feature=name_feature, value_txt_t9n={"en": "Propagation Test"}
        )
        ProductAttribute.objects.create(product=default_prod, feature=excluded_feature, value_bool=True)

        target = ProductFactory(
            shop=secondary_channel,
            feature_set=shared_feature_set,
            real_product=rp,
            inherit_attributes=True,
            inherit_descriptions=True,
        )

        # Act
        propagate_to_inheriting_products(default_prod)

        # Assert — excluded feature not propagated
        assert not ProductAttribute.objects.filter(product=target, feature=excluded_feature).exists()
        # Non-excluded feature IS propagated
        assert ProductAttribute.objects.filter(product=target, feature=name_feature).exists()
