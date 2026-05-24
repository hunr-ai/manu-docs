import asyncio
import importlib.util
import os
from pathlib import Path
import shutil
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from pytest_container.container import Container, ContainerData
from pytest_container.inspect import PortForwarding
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

import config.settings.settigns_loader as settings_loader_module


POSTGRES = Container(
    url="docker.io/library/postgres:18-alpine",
    forwarded_ports=[PortForwarding(container_port=5432)],
    extra_environment_variables={
        "POSTGRES_DB": "manudocsdb",
        "POSTGRES_USER": "manudocsuser",
        "POSTGRES_PASSWORD": "manudocs",
    },
)


def selected_container_runtime_exists() -> bool:
    runtime_choice = os.getenv("CONTAINER_RUNTIME", "podman").lower()
    return runtime_choice in {"podman", "docker"} and shutil.which(runtime_choice) is not None


CONTAINER_RUNTIME_MISSING = not selected_container_runtime_exists()

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "db"
    / "migrations"
    / "versions"
    / "20260524_0001_create_initial_schema.py"
)


def load_initial_migration() -> Any:
    spec = importlib.util.spec_from_file_location("initial_schema_migration", MIGRATION_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_initial_migration_identifiers() -> None:
    migration = load_initial_migration()

    assert migration.revision == "20260524_0001"
    assert migration.down_revision is None
    assert migration.branch_labels is None
    assert migration.depends_on is None
    assert migration.user_role_enum.name == "manudocs_user_role"
    assert migration.user_role_enum.enums == ["ADMIN", "OWNER", "VIEWER", "MEMBER"]


def test_initial_migration_upgrade_and_downgrade_operations(monkeypatch) -> None:
    migration = load_initial_migration()
    calls: list[tuple[str, Any]] = []

    class RecordingOp:
        @staticmethod
        def get_bind() -> object:
            return "bind"

        @staticmethod
        def create_table(name: str, *columns: object) -> None:
            calls.append(("create_table", {"name": name, "columns": columns}))

        @staticmethod
        def create_index(
            name: str, table_name: str, columns: list[str], unique: bool
        ) -> None:
            calls.append(
                (
                    "create_index",
                    {
                        "name": name,
                        "table_name": table_name,
                        "columns": columns,
                        "unique": unique,
                    },
                )
            )

        @staticmethod
        def drop_index(name: str, table_name: str) -> None:
            calls.append(("drop_index", {"name": name, "table_name": table_name}))

        @staticmethod
        def drop_table(name: str) -> None:
            calls.append(("drop_table", {"name": name}))

    monkeypatch.setattr(migration, "op", RecordingOp)
    monkeypatch.setattr(
        migration.user_role_enum,
        "create",
        lambda bind, checkfirst: calls.append(
            ("enum_create", {"bind": bind, "checkfirst": checkfirst})
        ),
    )
    monkeypatch.setattr(
        migration.user_role_enum,
        "drop",
        lambda bind, checkfirst: calls.append(
            ("enum_drop", {"bind": bind, "checkfirst": checkfirst})
        ),
    )

    migration.upgrade()
    migration.downgrade()

    assert [call[0] for call in calls] == [
        "enum_create",
        "create_table",
        "create_table",
        "create_index",
        "drop_index",
        "drop_table",
        "drop_table",
        "enum_drop",
    ]
    assert calls[1][1]["name"] == "manudocs_organizations"
    assert calls[2][1]["name"] == "manudocs_users"
    assert calls[3][1] == {
        "name": "ix_manudocs_users_organization_id_role",
        "table_name": "manudocs_users",
        "columns": ["organization_id", "role"],
        "unique": False,
    }


async def wait_for_database(url: str) -> None:
    engine = create_async_engine(url)
    try:
        for _ in range(30):
            try:
                async with engine.connect() as connection:
                    await connection.execute(text("select 1"))
                    return
            except Exception:
                await asyncio.sleep(1)
        raise TimeoutError("PostgreSQL container did not become ready")
    finally:
        await engine.dispose()


async def inspect_upgraded_database(url: str) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            tables = await connection.run_sync(
                lambda sync_connection: set(inspect(sync_connection).get_table_names())
            )
            assert tables >= {
                "alembic_version",
                "manudocs_organizations",
                "manudocs_users",
            }

            indexes = await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).get_indexes(
                    "manudocs_users"
                )
            )
            assert {
                "name": "ix_manudocs_users_organization_id_role",
                "column_names": ["organization_id", "role"],
                "unique": False,
            } in [
                {
                    "name": index["name"],
                    "column_names": index["column_names"],
                    "unique": index["unique"],
                }
                for index in indexes
            ]

            enum_labels = (
                await connection.execute(
                    text(
                        """
                        select enumlabel
                        from pg_enum
                        join pg_type on pg_type.oid = pg_enum.enumtypid
                        where pg_type.typname = 'manudocs_user_role'
                        order by enumsortorder
                        """
                    )
                )
            ).scalars().all()
            assert enum_labels == ["ADMIN", "OWNER", "VIEWER", "MEMBER"]
    finally:
        await engine.dispose()


async def inspect_downgraded_database(url: str) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            tables = await connection.run_sync(
                lambda sync_connection: set(inspect(sync_connection).get_table_names())
            )
            assert "manudocs_organizations" not in tables
            assert "manudocs_users" not in tables

            enum_count = (
                await connection.execute(
                    text(
                        "select count(*) from pg_type "
                        "where typname = 'manudocs_user_role'"
                    )
                )
            ).scalar_one()
            assert enum_count == 0
    finally:
        await engine.dispose()


@pytest.fixture
def alembic_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    monkeypatch.setattr(settings_loader_module, "BASE_DIR", config_dir)
    (config_dir / "dev.yaml").write_text("db:\n  pool-size: 5\n", encoding="utf-8")

    config = Config(str(Path(__file__).resolve().parents[1] / "db" / "alembic.ini"))
    config.attributes["settings_dir"] = config_dir
    return config


@pytest.mark.parametrize("container_per_test", [POSTGRES], indirect=True)
@pytest.mark.skipif(
    CONTAINER_RUNTIME_MISSING,
    reason="selected pytest-container runtime is not installed",
)
def test_initial_migration_upgrades_and_downgrades_postgres(
    container_per_test: ContainerData,
    alembic_config: Config,
) -> None:
    host_port = container_per_test.forwarded_ports[0].host_port
    settings_dir = alembic_config.attributes["settings_dir"]
    async_url = (
        "postgresql+asyncpg://manudocsuser:manudocs"
        f"@localhost:{host_port}/manudocsdb"
    )
    (settings_dir / "secrets.yaml").write_text(
        f"db:\n  url: {async_url}\n",
        encoding="utf-8",
    )

    asyncio.run(wait_for_database(async_url))
    command.upgrade(alembic_config, "head")
    asyncio.run(inspect_upgraded_database(async_url))

    command.downgrade(alembic_config, "base")
    asyncio.run(inspect_downgraded_database(async_url))