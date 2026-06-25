# Database Migrations (Alembic)

Phase 0.4 replaced hand-run `ALTER TABLE` statements with Alembic. New schema
changes are now generated and applied through migrations — no more manual SQL
that drifts between environments.

Config lives in `backend/alembic.ini` + `backend/alembic/`. The DB URL is taken
from `app.config.settings.DATABASE_URL_SYNC` (so it honours `.env`), and
`Base.metadata` is wired for `--autogenerate`. All commands run from `backend/`
(inside the backend container: `docker compose exec backend ...`).

## One-time adoption (per environment)

The current schema was built by `Base.metadata.create_all` (still kept for fresh
DBs), so we adopt Alembic without rewriting that history:

```bash
# Existing database that already has the tables:
alembic stamp 0001_baseline

# Brand-new database: create_all builds the tables on startup, then:
alembic stamp head
```

`alembic stamp` only records the revision as applied — it does not touch tables.

## Making a schema change from now on

1. Edit the SQLAlchemy models in `app/models/`.
2. Autogenerate the migration (diffs models vs. live DB):
   ```bash
   alembic revision --autogenerate -m "add X to runs"
   ```
3. **Review** the generated file in `alembic/versions/` (autogenerate is not
   infallible — check column types, server defaults, and data backfills).
4. Apply it:
   ```bash
   alembic upgrade head
   ```

## Useful commands

```bash
alembic current      # revision the DB is on
alembic heads        # latest revision(s) available
alembic history      # full history
alembic downgrade -1 # roll back one revision
```

## Note on `create_all`

`init_db()` still calls `Base.metadata.create_all` for convenience on fresh
databases. It only creates *missing* tables and never alters existing ones, so
it coexists safely with Alembic. The migration chain is the source of truth for
all incremental changes; once every environment is stamped, `create_all` can be
removed in a later phase.
