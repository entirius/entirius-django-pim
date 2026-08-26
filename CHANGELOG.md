# Changelog

## 3.2.0 — 2026-08-26

- Lookup provider (`services/lookup_provider`) — exposes RealProduct items, display data and
  freshness specs to `entirius-django-lookup`, so the dedup engine can see the PIM catalog.
  Registered by the host through `LOOKUP_PROVIDERS`; the provider registry is the only switch.
- `services/lookup_bridge` — the seam the product create hook uses to ask "do we already have
  this?"; `possible_duplicates` in the product create response, tagged `source=create_hook`.
- Provider hardening: `Product` `post_save` declared so renames refresh the fingerprint,
  batched display calls, language consistency, graceful degradation, and query-cost fixes
  on the provider/bridge path.

## 3.1.0 — 2026-08-06

- Product variant groups.
- Bundle data services and the `option_titles` system feature.

## 3.0.0 — 2026-07-09

- Initial public release: the product catalog core — products, variants,
  categories, attributes, features, media, and channel scoping.
- Admin API v2 with Pydantic schemas and OpenAPI docs.
- Enrichment adapter implementation for the content-quality bus.
- Migrations squashed into a single initial migration for the Entirius epoch.
