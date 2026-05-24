# Backend

This service uses typed YAML settings, SQLAlchemy models, and Alembic migrations.

## Common Commands

Run commands from this directory.

```bash
just test
just coverage
just migrate
just migration "describe schema change"
```

`just coverage` runs the backend tests with coverage and enforces the configured 96% minimum.

## Documentation

- [Configuration](../docs/backend/config.md)
- [Database and migrations](../docs/backend/database.md)
