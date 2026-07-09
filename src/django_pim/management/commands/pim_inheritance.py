# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Management command for PIM inheritance operations.

Usage:
  python manage.py pim_inheritance enable --channel default-europe
  python manage.py pim_inheritance enable --channel default-europe --flags attributes,descriptions
  python manage.py pim_inheritance enable --channel default-europe --sku PROD-001
  python manage.py pim_inheritance disable --channel default-europe
  python manage.py pim_inheritance materialize --channel default-europe
  python manage.py pim_inheritance audit
  python manage.py pim_inheritance audit --sku PROD-001
"""

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from django_pim.models import Channel, Product, ProductAttribute

VALID_FLAGS = {"attributes", "descriptions", "images"}


class Command(BaseCommand):
    help = "Manage inheritance between PIM channels."

    def add_arguments(self, parser):
        subparsers = parser.add_subparsers(dest="subcommand", help="Subcommand")
        subparsers.required = True

        # enable
        enable_parser = subparsers.add_parser("enable", help="Enable inheritance flags on products")
        enable_parser.add_argument("--channel", required=True, help="Channel idx")
        enable_parser.add_argument(
            "--flags",
            default="attributes,descriptions",
            help="Comma-separated flags: attributes,descriptions,images (default: attributes,descriptions)",
        )
        enable_parser.add_argument("--sku", help="Single product SKU (optional)")
        enable_parser.add_argument("--dry-run", action="store_true", help="Preview without changes")

        # disable
        disable_parser = subparsers.add_parser("disable", help="Disable all inheritance on a channel")
        disable_parser.add_argument("--channel", required=True, help="Channel idx")
        disable_parser.add_argument("--dry-run", action="store_true", help="Preview without changes")

        # materialize
        mat_parser = subparsers.add_parser("materialize", help="Re-sync inherited values + media from default channel")
        mat_parser.add_argument("--channel", help="Channel idx (optional, default: all inheriting)")
        mat_parser.add_argument("--dry-run", action="store_true", help="Preview without changes")

        # audit
        audit_parser = subparsers.add_parser("audit", help="Diagnostic report of inheritance state")
        audit_parser.add_argument("--sku", help="Audit a specific product across channels")

    def handle(self, *args, **options):
        subcommand = options["subcommand"]
        handler = getattr(self, f"_handle_{subcommand}")
        handler(options)

    def _handle_enable(self, options):
        channel_idx = options["channel"]
        flags_str = options.get("flags", "attributes,descriptions")
        sku = options.get("sku")
        dry_run = options.get("dry_run", False)

        flags = {f.strip() for f in flags_str.split(",")}
        invalid = flags - VALID_FLAGS
        if invalid:
            raise CommandError(f"Invalid flags: {invalid}. Valid: {VALID_FLAGS}")

        try:
            channel = Channel.objects.get(idx=channel_idx)
        except Channel.DoesNotExist:
            raise CommandError(f"Channel '{channel_idx}' not found")

        default_channel = Channel.objects.filter(is_default=True).first()
        if not default_channel:
            raise CommandError("No default channel. Set is_default=True first.")
        if channel.pk == default_channel.pk:
            raise CommandError("Cannot enable inheritance on the default channel.")

        # Ensure channel has inheritance_enabled
        if not channel.inheritance_enabled:
            if dry_run:
                self.stdout.write(
                    self.style.WARNING(f"Channel '{channel_idx}' has inheritance_enabled=False. Would set to True.")
                )
            else:
                channel.inheritance_enabled = True
                channel.save(update_fields=["inheritance_enabled"])
                self.stdout.write(f"Set inheritance_enabled=True on '{channel_idx}'")

        products = Product.objects.filter(shop=channel)
        if sku:
            products = products.filter(real_product__sku=sku)

        count = products.count()
        self.stdout.write(f"Found {count} product(s) on '{channel_idx}', flags: {sorted(flags)}")

        if dry_run:
            self.stdout.write(self.style.WARNING(f"DRY RUN: Would enable {sorted(flags)} on {count} product(s)"))
            return

        from django_pim.services.inheritance_service import materialize_inherited_media, materialize_inherited_values

        updated = 0
        skipped = 0
        for product in products.select_related("real_product", "feature_set"):
            if "attributes" in flags:
                product.inherit_attributes = True
            if "descriptions" in flags:
                product.inherit_descriptions = True
            if "images" in flags:
                product.inherit_images = True
            product.save(update_fields=["inherit_attributes", "inherit_descriptions", "inherit_images"])

            default_exists = Product.objects.filter(real_product=product.real_product, shop=default_channel).exists()
            if default_exists:
                if product.inherit_attributes or product.inherit_descriptions:
                    materialize_inherited_values(product)
                if product.inherit_images:
                    materialize_inherited_media(product)
                updated += 1
            else:
                self.stdout.write(
                    self.style.WARNING(f"  SKU '{product.sku}' has no product on default channel — skipped")
                )
                skipped += 1

        self.stdout.write(self.style.SUCCESS(f"Done: {updated} materialized, {skipped} skipped (no source)"))

    def _handle_disable(self, options):
        channel_idx = options["channel"]
        dry_run = options.get("dry_run", False)

        try:
            channel = Channel.objects.get(idx=channel_idx)
        except Channel.DoesNotExist:
            raise CommandError(f"Channel '{channel_idx}' not found")

        products = Product.objects.filter(shop=channel).filter(
            Q(inherit_attributes=True) | Q(inherit_descriptions=True) | Q(inherit_images=True)
        )
        count = products.count()

        if dry_run:
            self.stdout.write(self.style.WARNING(f"DRY RUN: Would disable inheritance on {count} product(s)"))
            return

        products.update(inherit_attributes=False, inherit_descriptions=False, inherit_images=False)
        ProductAttribute.objects.filter(product__shop=channel).update(overridden_langs=[])
        self.stdout.write(self.style.SUCCESS(f"Disabled inheritance on {count} product(s)"))

    def _handle_materialize(self, options):
        channel_idx = options.get("channel")
        dry_run = options.get("dry_run", False)

        products = Product.objects.filter(shop__inheritance_enabled=True).filter(
            Q(inherit_attributes=True) | Q(inherit_descriptions=True) | Q(inherit_images=True)
        )
        if channel_idx:
            try:
                channel = Channel.objects.get(idx=channel_idx)
            except Channel.DoesNotExist:
                raise CommandError(f"Channel '{channel_idx}' not found")
            products = products.filter(shop=channel)

        count = products.count()

        if dry_run:
            self.stdout.write(self.style.WARNING(f"DRY RUN: Would re-materialize {count} product(s)"))
            return

        from django_pim.services.inheritance_service import materialize_inherited_media, materialize_inherited_values

        updated = 0
        errors = 0
        for product in products.select_related("real_product", "shop", "feature_set"):
            try:
                if product.inherit_attributes or product.inherit_descriptions:
                    materialize_inherited_values(product)
                if product.inherit_images:
                    materialize_inherited_media(product)
                updated += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  Error on SKU '{product.sku}': {e}"))
                errors += 1

        self.stdout.write(self.style.SUCCESS(f"Materialized: {updated} updated, {errors} errors"))

    def _handle_audit(self, options):
        sku = options.get("sku")

        default_channel = Channel.objects.filter(is_default=True).first()
        if not default_channel:
            self.stdout.write(self.style.ERROR("No default channel configured"))
            return

        if sku:
            self._audit_sku(sku, default_channel)
        else:
            self._audit_all(default_channel)

    def _audit_all(self, default_channel):
        default_count = Product.objects.filter(shop=default_channel).count()
        self.stdout.write(f"Default channel: {default_channel.idx} ({default_count} products)")
        self.stdout.write("")

        channels = Channel.objects.exclude(pk=default_channel.pk).order_by("idx")
        for channel in channels:
            total = Product.objects.filter(shop=channel).count()
            inh_attr = Product.objects.filter(shop=channel, inherit_attributes=True).count()
            inh_desc = Product.objects.filter(shop=channel, inherit_descriptions=True).count()
            inh_img = Product.objects.filter(shop=channel, inherit_images=True).count()

            enabled = "ON" if channel.inheritance_enabled else "OFF"
            defaults = channel.default_inheritance_flags or []

            self.stdout.write(f"  {channel.idx}: {total} products (inheritance: {enabled}, defaults: {defaults})")
            self.stdout.write(
                f"    inherit_attributes: {inh_attr}, inherit_descriptions: {inh_desc}, inherit_images: {inh_img}"
            )
            self.stdout.write("")

    def _audit_sku(self, sku, default_channel):
        self.stdout.write(f"Auditing SKU: {sku}")
        self.stdout.write(f"Default channel: {default_channel.idx}")
        self.stdout.write("")

        products = (
            Product.objects.filter(real_product__sku=sku)
            .select_related("shop", "feature_set", "real_product")
            .order_by("shop__idx")
        )

        if not products.exists():
            self.stdout.write(self.style.ERROR(f"No products found with SKU '{sku}'"))
            return

        for product in products:
            is_default = product.shop_id == default_channel.pk
            status = " (DEFAULT)" if is_default else ""
            flags = []
            if product.inherit_attributes:
                flags.append("attr")
            if product.inherit_descriptions:
                flags.append("desc")
            if product.inherit_images:
                flags.append("img")
            flags_str = f" [{','.join(flags)}]" if flags else ""

            self.stdout.write(f"  Channel: {product.shop.idx}{status}{flags_str}")
            self.stdout.write(f"    Feature set: {product.feature_set.idx}")

            if flags and not is_default:
                attrs = ProductAttribute.objects.filter(product=product).select_related("feature")
                for attr in attrs:
                    overridden = attr.overridden_langs or []
                    status = "overridden" if overridden else "inherited"
                    langs_info = f" (langs: {', '.join(overridden)})" if overridden else ""
                    self.stdout.write(f"      {attr.feature.idx}: {status}{langs_info}")

            self.stdout.write("")
