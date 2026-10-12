---
title: Testing
description: "PIM test suite: PostgreSQL requirement, slow tests, factories and the golden fixture."
---

Requires PostgreSQL 15 or newer (`UniqueConstraint(nulls_distinct=False)`): set `DATABASE_URL` (the default in
`tests/settings.py` points at a local postgres). Opt-in `@pytest.mark.slow` tests are deselected by default
(`addopts = -m "not slow"`); run them with `-m slow`.

```bash
make test                                                                        # slow tests skipped
DATABASE_URL=postgresql://… uv run pytest tests/ -x -q                           # custom postgres
PIM_PERF_N=10000 uv run pytest tests/test_perf_gaps.py -m slow -s -q             # perf calibration
```

| File | Scope |
|------|-------|
| `test_admin_api.py` | Read-only (list, retrieve, auth, pagination) |
| `test_admin_api_crud.py` | Full CRUD: products, categories, features, feature sets, attributes, attributes groups |
| `test_admin_api_links.py` | LinkType CRUD + ProductLink CRUD + auth + constraints |
| `test_admin_api_pictures.py` | Upload + SHA1 dedup + gallery CRUD + role constraints |
| `test_admin_api_files.py` | FilesCategory CRUD + upload + ProductFile link/unlink |
| `test_admin_api_videos.py` | ProductVideo CRUD + source auto-detect + role constraints |
| `test_admin_api_inheritance.py` | Inheritance: channel default, materialization, propagation, copy, add-to-channel, toggle, API endpoints |
| `test_models.py` | Quality gaps: GapDefinition/GapFinding constraints + defaults, Product rollup columns, FK CASCADE, silent `.update()`, seed idempotency |
| `test_services.py` | Gap detection + rollup repair / propagation hook |
| `test_signals_gaps_dispatch.py` | Gap debounce: own `pim:gaps:*` keys, own flush task/queue, coalesce, Redis degradation |
| `test_signals_gaps.py` | Gap on-save enqueue (independent of Matrix flag) + GapDefinition lifecycle (fast path / stale / cleanup) |
| `test_tasks_gaps.py` | Flush→detect, batch==per-product, full-lock coalesce, nightly stale/fresh/locked |
| `test_api_gaps.py` | Gap admin API: GapDefinition CRUD + auth, bulk findings, exemptions CRUD, recompute/status, product soft-compat (gap_* + sort/filter), 500-no-leak |
| `test_gap_exemptions.py` | Deep mute: detection skip per pair/language/neutral slot, create→finding gone + silent rollup, delete→restored, service validation |
| `test_correctness_golden.py` | Golden correctness, fixtures-driven: FeatureSet applicability, custom "unevaluated", MULTISELECT/DECIMAL emptiness, inherited→source_channel + cleanup-after-propagation E2E, fixture-drift guard |
| `test_concurrency.py` | Concurrency manifest: idempotency, full-lock coalesce, severity fast-path, cleanup, silent rollup (no loop), disjoint-batch isolation |
| `test_perf_gaps.py` | `recompute_range` calibration (opt-in `@pytest.mark.slow`) |
| `test_enrichment_adapter.py`, `test_lookup_provider.py`, `test_lookup_bridge.py` | The enrichment and lookup boundaries |
| `test_access_ownership.py` | Every admin route carries an access area |
| `test_api.py` | Legacy v1 |

Factories in `tests/factories.py`: Channel, Feature, FeatureSet, Attribute, AttributesGroup, RealProduct, Product, ProductCategory, ProductAttribute, FeatureInFeatureSet, ProductLinkType, ProductLink, FilesCategory, GapDefinition, GapFinding.

Golden-gaps fixture: `tests/fixtures/gaps_golden.yaml` (deterministic catalogue — channels, features, rules, products), mirrored in `entirius-test-package-emporium/fixtures/django_pim_gaps_golden.cfg.yaml` for seed/init reuse. Regenerable via `tests/_golden_data.py::emit_fixture` (builds in a rolled-back transaction, serialises to YAML).
