---
title: Inheritance
description: How PIM products inherit attributes, descriptions, and media from a default channel
---

## Overview

Inheritance lets products on secondary channels receive data from a **default channel** automatically. Three independent flags control what gets inherited:

| Flag | What it covers |
|------|----------------|
| `inherit_attributes` | All features except name, description, short_description |
| `inherit_descriptions` | name, description, short_description |
| `inherit_images` | Pictures, videos, files |

Any combination works. A product can inherit attributes + images but keep its own descriptions, or vice versa.

**Not inherited** — these are always per-channel:

| Field | Reason |
|-------|--------|
| Visibility | Channel-specific merchandising decisions |
| Enabled/disabled | Channel-specific availability |
| Categories | Different category trees per channel |
| Prices | Different pricing per channel/currency |
| Product links | Different cross-sell/upsell per channel |

## Architecture (Big Picture)

```
Default Channel (source of truth)
    Product A (SKU-001)
        attributes: color=red, weight=1.5kg
        descriptions: name="Chair", description="A nice chair"
        media: 3 pictures, 1 video
            │
            ├── propagate on change ──►  Channel Europe (inherit_attributes=true, inherit_descriptions=true)
            │                               Product A (SKU-001) ← materialized values
            │
            └── propagate on change ──►  Channel US (inherit_images=true)
                                            Product A (SKU-001) ← materialized media
```

**Write-time materialization**: inherited values are physically stored on the target product. Matrix sync, Cynthia, CSV importers read them with zero changes needed.

## Prerequisites

Two things must be true for inheritance to work:

1. **Channel.inheritance_enabled = True** on the target channel (master switch)
2. **At least one flag** (`inherit_attributes`, `inherit_descriptions`, `inherit_images`) set on the product

The `inheritance_enabled` flag is a channel-level gate. If it's `False`, no product on that channel inherits anything, regardless of per-product flags.

## Setting Up Inheritance

### Step 1: Configure the default channel

One channel must have `is_default=True`. Set via Django admin or directly in DB. The default channel is protected from deletion.

### Step 2: Enable inheritance on target channel

```bash
# Via management command (recommended for bulk operations)
python manage.py pim_inheritance enable --channel=default-europe --dry-run
python manage.py pim_inheritance enable --channel=default-europe

# This sets inheritance_enabled=True on the channel and
# sets inherit_attributes + inherit_descriptions on all products
```

The command also materializes values from the default channel immediately.

### Step 3: Verify

```bash
python manage.py pim_inheritance audit
```

Output shows per-channel inheritance status: how many products inherit, which flags are active.

## How Materialization Works

When inheritance flags are enabled on a product:

1. Find the same RealProduct (same SKU) on the default channel
2. Get the **eligible features**: FeatureSet intersection between source and target, plus all system features present on the source product
3. For each eligible feature:
   - Check if it's a "description" feature (`name`, `description`, `short_description`) or a regular attribute
   - Check the matching flag (`inherit_descriptions` or `inherit_attributes`)
   - Copy values, respecting `overridden_langs` (see Override Behavior below)
4. For media (when `inherit_images=True`): delete old inherited media, copy fresh from default

## Override Behavior

Overrides work at **per-language, per-attribute** granularity:

| `overridden_langs` | Meaning |
|---|---|
| `[]` | All languages inherit from default |
| `["en"]` | English is user-controlled, other languages inherit |
| `["*"]` | Entire value overridden (used for non-t9n attributes like bool/decimal) |

Toggle per-language overrides via `POST .../products/{sku}/toggle-override/` or the CMS inheritance field toggle.

## Propagation

When a product on the default channel is updated, changes push automatically to all inheriting products:

- **Attribute changes**: re-materialize affected features on inheriting products
- **Media changes** (pictures/videos/files added/removed): re-materialize media on products with `inherit_images=True`
- **Scope**: only products with the same RealProduct (same SKU) and relevant flag enabled

Propagation runs synchronously. For scale, use the Celery task.

## CMS Usage

On non-default channels, the product detail toolbar shows an **Inheritance** button (when `inheritance_enabled=True` on the channel). Click to toggle the 3 flags individually. Count badge shows how many flags are active.

Description fields (name, description) show per-language toggle buttons when `inherit_descriptions=True`:
- **Linked** (green dot): inherited from default, read-only
- **Cut** (grey dot): user-controlled, editable

## Copy vs Inherit

| | Copy | Inherit |
|---|---|---|
| **Action** | One-time snapshot | Ongoing sync |
| **API** | `POST .../copy-attributes/` | `PATCH` with flag = true |
| **Override tracking** | Copied values marked as overridden | Non-overridden values sync automatically |
| **Use case** | "Take defaults as starting point, then edit freely" | "Keep in sync, override only what differs" |

## Add to Channel

Create the same product on another channel:

```
POST /api/pim/v2/admin/{channel}/products/{sku}/add-to-channel/
{
  "target_channel_idx": "europe",
  "copy_content": true
}
```

Inheritance flags are set separately after the product exists, via PATCH or the CMS Inheritance button.

## API Endpoints

| Method | URL | Purpose |
|---|---|---|
| PATCH | `.../products/{sku}/` | Set `inherit_attributes`, `inherit_descriptions`, `inherit_images` |
| POST | `.../products/{sku}/copy-attributes/` | One-time copy from source channel |
| POST | `.../products/{sku}/add-to-channel/` | Create product on another channel |
| POST | `.../products/{sku}/toggle-override/` | Toggle language override per attribute |
| POST | `.../products/{sku}/toggle-media-override/` | Toggle media item between inherited/local |
| GET | `.../channels/` | Includes `inheritance_enabled`, `default_inheritance_flags` |
| GET | `.../products/{sku}/` | Includes all 3 flags, `default_channel_idx`, per-attribute `overridden_langs` |

## Channel Configuration

| Field | Type | Purpose |
|---|---|---|
| `inheritance_enabled` | bool | Master switch. False = no inheritance on this channel |
| `default_inheritance_flags` | JSON list | Defaults for the management command, e.g. `["attributes", "descriptions"]` |

## Edge Cases

| Scenario | Behavior |
|---|---|
| Product only on secondary (not on default) | Flags set but no materialization — values stay as entered |
| FeatureSet mismatch | Only business-unit features in both FeatureSets participate; system features always participate |
| Default channel deleted | Protected — raises ProtectedError |
| Default channel changed | Run `pim_inheritance materialize` to re-sync |
| Product deleted on default | Inheriting products keep materialized values |
| MULTISELECT features | All rows replaced atomically (no per-row override) |
| SELECT features | `attribute` FK is copied correctly |
| Local media + inherit_images | Local media preserved, inherited media added alongside |

## Excluding Features from Inheritance

Some features need to remain channel-independent even when inheritance is enabled — e.g. a channel-specific badge, local regulatory label, or channel-specific extension data.

Set `exclude_from_inheritance=True` on a Feature to exclude it from inheritance entirely:

```
PATCH /api/pim/v2/admin/features/{idx}/
{"exclude_from_inheritance": true}
```

When a feature has this flag:
- Materialization skips it — no values are copied from the default channel
- Propagation skips it — default channel updates don't push to inheriting products
- The flag applies regardless of `inherit_attributes` or `inherit_descriptions` settings on the product
- Each channel manages that feature's value independently

Default is `false` (inheritable, preserving current behavior). This is a Feature-level setting, similar to `is_required` or `is_filterable`.

## Description Feature Classification

Features are classified based on their `idx`:

```python
DESCRIPTION_FEATURE_IDXS = {"name", "description", "short_description"}
```

- Features with idx in this set are governed by `inherit_descriptions`
- All other features are governed by `inherit_attributes`

This is a code-level constant in `django_pim/settings.py`.
