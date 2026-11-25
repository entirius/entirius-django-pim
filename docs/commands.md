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


---

## pim_fill_url_keys

Fill the missing product `url_key`. The storefront opens a product page by it (matrix matches it exactly and has no
unique constraint), so a product without one is "not found" and a duplicate opens the wrong product. A key is
`slug(name)-slug(sku)` for every language that has a name, unique within the channel for that language (`-2`, `-3`…
on collision, never longer than 200 characters). A key that is already set is never changed, so a second run finds
nothing. Disabled and hidden products count as taken. Product create and add-to-channel apply the same rule.

```bash
python manage.py pim_fill_url_keys                              # preview, every channel
python manage.py pim_fill_url_keys --channel=default-europe     # one channel
python manage.py pim_fill_url_keys --apply                      # write
```

Prints one `channel  sku  lang  key` line per key and a count. Without `--apply` nothing is written; the preview
reserves the keys it picks, so it is exactly what `--apply` writes. Every run ends with a read-only report of the
duplicates already stored (`DUPLICATE  channel  lang  key  sku, sku`); it never rewrites them (live URLs) and does
not change the exit code.

Other rules the service enforces, in every write path:

- A key a user gives (create, product edit) that another product of the channel already has for that language is a
  400 naming the language and the SKU. An unchanged key is not re-checked, so an old duplicate does not block an
  unrelated edit.
- A key that arrives by copy or inheritance (add-to-channel, copy-attributes, propagation from the default channel,
  switching a language back to inherited) is suffixed when taken and stays overridden, so the next propagation does
  not turn it back into a duplicate.
- A name change never regenerates a key (stable URLs).
- Writes run under a per-channel advisory lock (`pg_advisory_xact_lock`), so concurrent writers cannot pick the
  same key.
