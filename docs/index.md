---
title: "PIM"
description: "Product Information Management module — the core of the Volkanos product catalog."
sidebar:
  label: "Overview"
  collapsed: true
---

PIM (`django-pim`) manages the product catalog: products, variants, categories, attributes, features, pricing, and media.

## Key Concepts

- **RealProduct** — the physical item (SKU, EAN). Shared across channels.
- **Product** — a channel-specific projection of a RealProduct (visibility, pricing, enabled state).
- **Channel** — a sales channel (storefront). Each channel sees its own product subset.
- **ProductCategory** — hierarchical category tree per channel.
- **Feature / FeatureSet** — filterable product properties (color, size, material).
- **Attribute** — key-value metadata attached to products (dimensions, weight).

## Product Types

PIM supports four product types via model inheritance from `Product`:

| Type | Model | Use case |
|------|-------|----------|
| Simple | `ProductSimple` | Standard single-SKU product |
| Configurable | `ProductConfigurable` | Parent with selectable variants (size, color) |
| Bundle | `ProductBundle` | Fixed or optional grouping of other products |
| Custom | `ProductCustom` | Customizable product with user input |

## Cross-Channel Inheritance

Products on secondary channels can inherit data from the **default channel** via three independent flags: attributes, descriptions, and media. The system uses write-time materialization — inherited values are physically stored, so downstream consumers (Matrix, Cynthia, CSV) work without changes.

See [Inheritance](./inheritance/) for setup, API, and override behavior.

## Related Modules

- **[Quality Gaps](./quality/)** — what each product is missing, per channel and language
- **[PIM CSV](./pim-csv/)** — bulk CSV importer for PIM data
- **[PIM Translator](./pim-translator/)** — AI translation bridge for PIM entities
- **[Database Diagrams](./erd/)** — auto-generated ER diagrams for all PIM models

## Signal-Driven Sync

PIM publishes Django signals on model changes (Product, ProductAttribute, Feature, Attribute, etc.) that trigger automatic Matrix read model sync via Celery tasks. Disabled by default — enable via `PimSettings.matrix_signals_enabled` in Django admin.

See [Signal-Driven Sync](/architecture/signal-driven-sync/) for full architecture.

## API

PIM exposes admin endpoints under `/api/pim/v2/admin/` for product CRUD, category management, and attribute handling. See the [API Reference](/api/) for details.
