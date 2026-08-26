---
title: Management Commands
description: PIM management commands reference
---

## pim_inheritance

Manage product inheritance between PIM channels. See [Inheritance](./inheritance/) for concepts.

### enable

Enable inheritance flags on products and materialize values from the default channel.

```bash
# Default: attributes + descriptions
python manage.py pim_inheritance enable --channel=default-europe

# All 3 flags
python manage.py pim_inheritance enable --channel=default-europe --flags=attributes,descriptions,images

# Single product
python manage.py pim_inheritance enable --channel=default-europe --sku=SKU-001

# Preview only
python manage.py pim_inheritance enable --channel=default-europe --dry-run
```

The `--flags` parameter accepts a comma-separated list: `attributes`, `descriptions`, `images`. Default is `attributes,descriptions`.

Also sets `Channel.inheritance_enabled=True` if not already set.

### disable

Turn off all inheritance flags and clear override tracking. Materialized values remain — no data loss.

```bash
python manage.py pim_inheritance disable --channel=default-europe
python manage.py pim_inheritance disable --channel=default-europe --dry-run
```

### materialize

Re-sync inherited values and media from the default channel. Useful after bulk imports, changing the default channel, or as a repair tool.

```bash
# All channels with inheritance
python manage.py pim_inheritance materialize

# Specific channel
python manage.py pim_inheritance materialize --channel=default-europe

# Preview
python manage.py pim_inheritance materialize --dry-run
```

### audit

Read-only diagnostic report. Shows inheritance state per channel and per product.

```bash
# All channels
python manage.py pim_inheritance audit

# Single product across all channels
python manage.py pim_inheritance audit --sku=SKU-001
```

Example output:

```
Default channel: default-local (33 products)

  default-europe: 33 products (inheritance: ON, defaults: ['attributes', 'descriptions'])
    inherit_attributes: 33, inherit_descriptions: 33, inherit_images: 0
```

### Common Scenarios

#### Initial setup after import

```bash
python manage.py products-import-from-csv default-local products.csv
python manage.py products-import-from-csv default-europe products-eu.csv
python manage.py pim_inheritance enable --channel=default-europe
python manage.py pim_inheritance audit
```

#### Enable images inheritance on existing channel

```bash
python manage.py pim_inheritance enable --channel=default-europe --flags=images
```

This adds `inherit_images=True` without touching existing attribute/description flags.

#### Full reset and re-enable

```bash
python manage.py pim_inheritance disable --channel=default-europe
python manage.py pim_inheritance enable --channel=default-europe --flags=attributes,descriptions,images
```

#### Repair after default channel data change

```bash
python manage.py pim_inheritance materialize --channel=default-europe
python manage.py pim_inheritance audit
```
