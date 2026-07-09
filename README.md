# Django PIM

Product Information Management module for Volkanos.

## Quick Start

Requires Python 3.11+ and PostgreSQL 15+ (`UniqueConstraint(nulls_distinct=False)`).

```bash
make install                     # uv sync, incl. extras
make test                        # pytest against DATABASE_URL
```

Tests read `DATABASE_URL` (default `postgresql://postgres:postgres@localhost:5432/test` —
matches the CI service).

### Other commands

```bash
make check    # ruff check + format-check
make fix      # auto-fix lint + format
```

## Details

See `AGENTS.md` for architecture, API endpoints, models, and gotchas.
