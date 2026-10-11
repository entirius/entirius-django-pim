---
title: Gotchas
description: Further pitfalls of the PIM module; the most frequent ones are in AGENTS.md.
---

The gotchas an agent meets most often are in `AGENTS.md` § Gotchas; the rest are kept here.

- `AttributesGroup.idx` was missing unique constraint before migration 0048
- `ProductLinkType` was migrated from IntEnumChoices to a Django model (migrations 0049-0050). Old int values map to PKs: 1=related, 2=crosssell, 3=upsell, 4=navigation
- Picture upload: SHA1 is computed in both the service (for dedup check) and the model's `save()` (for storage). They use the same algorithm
- Videos are URL-based only (no file upload). Video.save() auto-detects source from URL (YouTube/Vimeo)
- Propagation is synchronous by default; use Celery task for async at scale
- Media inheritance copies pictures/videos/files with `is_inherited=True`; local media (`is_inherited=False`) preserved during re-materialization
- **`picture_alt` proposals carry STRING picture-pk keys** — `proposed_value`/`current_snapshot` are JSON, so `{"alts": {"42": "alt"}}`, never int keys. Apply validates every pk against the product BEFORE writing (unknown/foreign pk → `ValueError`, zero partial writes); revert with `{"alts": {}}` is a legit no-op (no pictures at intake), unlike `feature_set` where an empty snapshot is a hard error
