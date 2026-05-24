# Backend Database

The backend database layer lives under `backend/db`. SQLAlchemy models define the schema, Alembic versions it, and tests exercise migrations against a temporary PostgreSQL container with `pytest-container`.

## Model Layout

Common columns are defined by `BaseModel` in `backend/db/models/base_model.py`:

- `id`
- `created_at`
- `updated_at`

Application tables are exported from `backend/db/models/__init__.py` so Alembic can build one metadata graph from `BaseModel.metadata`.

The current schema contains:

- `manudocs_organizations`
- `manudocs_users`
- `manudocs_user_role`
- `ix_manudocs_users_organization_id_role`

## Alembic

Alembic is configured by `backend/db/alembic.ini`. The configured script location is `backend/db/migrations`, and the live database URL is loaded by `backend/db/migrations/env.py` through `SettingsLoader().load_settings_sync()`.

Development database URLs can be provided in `backend/config/values/secrets.yaml`:

```yaml
db:
  url: postgresql+asyncpg://manudocsuser:manudocs@localhost:5432/manudocsdb
```

## Local Commands

Run database commands from the backend directory.

Create a migration:

```bash
just migration "describe schema change"
```

Apply migrations:

```bash
just migrate
```

Downgrade one revision:

```bash
just downgrade
```

Show current revision:

```bash
just db-current
```

## Testing

Database tests live with the other backend tests under `backend/tests`.

Fast tests assert the SQLAlchemy metadata shape directly. Migration tests use `pytest-container` to launch `postgres:18-alpine`, map port `5432` to a free host port, write a temporary settings directory, and run Alembic upgrade/downgrade against that disposable database.

Run the full backend test suite with coverage:

```bash
just coverage
```

Coverage is configured in `backend/pyproject.toml` and must stay above 96%.

## Container Runtime

`pytest-container` uses an available OCI runtime. It defaults to Podman when available and can use Docker. To force Docker:

```bash
CONTAINER_RUNTIME=docker just coverage
```