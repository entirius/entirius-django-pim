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


---

## pim-thumbs-generate

Generate thumbnails for the pictures of a channel, from `THUMBS_CONFIG` (products) and
`CATEGORY_THUMBS_CONFIG` (category pictures, skipped with `--sku`).

```bash
python manage.py pim-thumbs-generate default-europe
python manage.py pim-thumbs-generate default-europe --sku=SKU-001
python manage.py pim-thumbs-generate default-europe --missing-only
python manage.py pim-thumbs-generate default-europe --clean
```

| Option | Effect |
|--------|--------|
| `--sku` | Only the pictures of one product |
| `--missing-only` | Only pictures lacking at least one configured thumbnail |
| `--clean` | Delete existing thumbnails of the selected pictures first |

The last line is a summary: `Thumbnails: generated N, already present N, failed N (pictures found: N)`.
The command exits non-zero when `THUMBS_CONFIG` is not set, when it found no pictures, or when every
thumbnail it tried failed. A run where only some thumbnails fail still exits 0; read the `failed` count.
With `--missing-only` and nothing missing it exits 0 and says so. The resizer creates `TMP_DIR` when it is absent.
