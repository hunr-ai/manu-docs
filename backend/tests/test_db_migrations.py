import asyncio
import importlib.util
import os
import shutil
from pathlib import Path
from typing import Any

import config.settings.settings_loader as settings_loader_module
import pytest
from alembic import command
from alembic.config import Config
from pytest_container.container import Container, ContainerData
from pytest_container.inspect import PortForwarding
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

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
    return (
        runtime_choice in {"podman", "docker"}
        and shutil.which(runtime_choice) is not None
    )


CONTAINER_RUNTIME_MISSING = not selected_container_runtime_exists()

INITIAL_MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "db"
    / "migrations"
    / "versions"
    / "20260524_0001_create_initial_schema.py"
)
EMAIL_TEMPLATES_MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "db"
    / "migrations"
    / "versions"
    / "20260524_0002_add_email_templates.py"
)
EMAIL_TRACKS_MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "db"
    / "migrations"
    / "versions"
    / "20260524_0003_add_email_tracks.py"
)
ALLOW_USERS_WITHOUT_ORGANIZATION_MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "db"
    / "migrations"
    / "versions"
    / "20260524_0004_allow_users_without_organization.py"
)


def load_migration(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_initial_migration() -> Any:
    return load_migration(INITIAL_MIGRATION_PATH, "initial_schema_migration")


def load_email_templates_migration() -> Any:
    return load_migration(EMAIL_TEMPLATES_MIGRATION_PATH, "email_templates_migration")


def load_email_tracks_migration() -> Any:
    return load_migration(EMAIL_TRACKS_MIGRATION_PATH, "email_tracks_migration")


def load_allow_users_without_organization_migration() -> Any:
    return load_migration(
        ALLOW_USERS_WITHOUT_ORGANIZATION_MIGRATION_PATH,
        "allow_users_without_organization_migration",
    )


def test_initial_migration_identifiers() -> None:
    migration = load_initial_migration()

    assert migration.revision == "20260524_0001"
    assert migration.down_revision is None
    assert migration.branch_labels is None
    assert migration.depends_on is None
    assert migration.user_role_enum.name == "manudocs_user_role"
    assert migration.user_role_enum.enums == ["ADMIN", "OWNER", "VIEWER", "MEMBER"]
    assert migration.user_role_enum.create_type is False


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


def test_email_templates_migration_identifiers() -> None:
    migration = load_email_templates_migration()

    assert migration.revision == "20260524_0002"
    assert migration.down_revision == "20260524_0001"
    assert migration.branch_labels is None
    assert migration.depends_on is None


def test_email_templates_migration_upgrade_and_downgrade_operations(
    monkeypatch,
) -> None:
    migration = load_email_templates_migration()
    calls: list[tuple[str, Any]] = []

    class RecordingOp:
        @staticmethod
        def create_table(name: str, *columns: object) -> None:
            calls.append(("create_table", {"name": name, "columns": columns}))

        @staticmethod
        def bulk_insert(table: object, rows: list[dict[str, str]]) -> None:
            calls.append(("bulk_insert", {"table": table, "rows": rows}))

        @staticmethod
        def drop_table(name: str) -> None:
            calls.append(("drop_table", {"name": name}))

    monkeypatch.setattr(migration, "op", RecordingOp)

    migration.upgrade()
    migration.downgrade()

    assert [call[0] for call in calls] == [
        "create_table",
        "bulk_insert",
        "drop_table",
    ]
    assert calls[0][1]["name"] == "manudocs_email_templates"
    columns = calls[0][1]["columns"]
    assert [column.name for column in columns[:5]] == [
        "name",
        "use_case",
        "subject",
        "html_template",
        "text_template",
    ]
    assert calls[1][1]["rows"] == [
        {
            "name": "Login code",
            "use_case": "login",
            "subject": "Your ManuDocs login code",
            "html_template": (
                "<p>Your ManuDocs login code is <strong>{{ otp }}</strong>.</p>\n"
                "<p>This code expires soon. If you did not request it, you can ignore this email.</p>"
            ),
            "text_template": (
                "Your ManuDocs login code is {{ otp }}.\n\n"
                "This code expires soon. If you did not request it, you can ignore this email."
            ),
        }
    ]
    assert calls[2][1] == {"name": "manudocs_email_templates"}


def test_email_tracks_migration_identifiers() -> None:
    migration = load_email_tracks_migration()

    assert migration.revision == "20260524_0003"
    assert migration.down_revision == "20260524_0002"
    assert migration.branch_labels is None
    assert migration.depends_on is None


def test_email_tracks_migration_upgrade_and_downgrade_operations(
    monkeypatch,
) -> None:
    migration = load_email_tracks_migration()
    calls: list[tuple[str, Any]] = []

    class RecordingOp:
        @staticmethod
        def create_table(name: str, *columns: object) -> None:
            calls.append(("create_table", {"name": name, "columns": columns}))

        @staticmethod
        def create_index(
            name: str,
            table_name: str,
            columns: list[str],
            unique: bool,
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

    migration.upgrade()
    migration.downgrade()

    assert [call[0] for call in calls] == [
        "create_table",
        "create_index",
        "drop_index",
        "drop_table",
    ]
    assert calls[0][1]["name"] == "manudocs_email_tracks"
    columns = calls[0][1]["columns"]
    assert [column.name for column in columns[:8]] == [
        "recipient",
        "subject",
        "status",
        "tracking_token",
        "sent_at",
        "read_at",
        "provider_message_id",
        "failure_reason",
    ]
    assert calls[1][1] == {
        "name": "ix_manudocs_email_tracks_tracking_token",
        "table_name": "manudocs_email_tracks",
        "columns": ["tracking_token"],
        "unique": True,
    }
    assert calls[2][1] == {
        "name": "ix_manudocs_email_tracks_tracking_token",
        "table_name": "manudocs_email_tracks",
    }
    assert calls[3][1] == {"name": "manudocs_email_tracks"}


def test_allow_users_without_organization_migration_identifiers() -> None:
    migration = load_allow_users_without_organization_migration()

    assert migration.revision == "20260524_0004"
    assert migration.down_revision == "20260524_0003"
    assert migration.branch_labels is None
    assert migration.depends_on is None


def test_allow_users_without_organization_migration_operations(monkeypatch) -> None:
    migration = load_allow_users_without_organization_migration()
    calls: list[tuple[str, Any]] = []

    class RecordingOp:
        @staticmethod
        def alter_column(
            table_name: str,
            column_name: str,
            existing_type: object,
            nullable: bool,
        ) -> None:
            calls.append(
                (
                    "alter_column",
                    {
                        "table_name": table_name,
                        "column_name": column_name,
                        "existing_type": existing_type,
                        "nullable": nullable,
                    },
                )
            )

    monkeypatch.setattr(migration, "op", RecordingOp)

    migration.upgrade()
    migration.downgrade()

    assert [call[0] for call in calls] == ["alter_column", "alter_column"]
    assert calls[0][1]["table_name"] == "manudocs_users"
    assert calls[0][1]["column_name"] == "organization_id"
    assert calls[0][1]["nullable"] is True
    assert calls[1][1]["table_name"] == "manudocs_users"
    assert calls[1][1]["column_name"] == "organization_id"
    assert calls[1][1]["nullable"] is False


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
                "manudocs_email_templates",
                "manudocs_email_tracks",
                "manudocs_organizations",
                "manudocs_users",
            }

            email_template_columns = await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).get_columns(
                    "manudocs_email_templates"
                )
            )
            assert [column["name"] for column in email_template_columns] == [
                "name",
                "use_case",
                "subject",
                "html_template",
                "text_template",
                "id",
                "created_at",
                "updated_at",
            ]

            login_template = (
                await connection.execute(
                    text(
                        """
                        select subject, html_template, text_template
                        from manudocs_email_templates
                        where use_case = 'login'
                        """
                    )
                )
            ).one()
            assert login_template.subject == "Your ManuDocs login code"
            assert "{{ otp }}" in login_template.html_template
            assert "{{ otp }}" in login_template.text_template

            email_track_columns = await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).get_columns(
                    "manudocs_email_tracks"
                )
            )
            assert [column["name"] for column in email_track_columns] == [
                "recipient",
                "subject",
                "status",
                "tracking_token",
                "sent_at",
                "read_at",
                "provider_message_id",
                "failure_reason",
                "id",
                "created_at",
                "updated_at",
            ]

            email_track_indexes = await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).get_indexes(
                    "manudocs_email_tracks"
                )
            )
            assert {
                "name": "ix_manudocs_email_tracks_tracking_token",
                "column_names": ["tracking_token"],
                "unique": True,
            } in [
                {
                    "name": index["name"],
                    "column_names": index["column_names"],
                    "unique": index["unique"],
                }
                for index in email_track_indexes
            ]

            indexes = await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).get_indexes(
                    "manudocs_users"
                )
            )
            user_columns = await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).get_columns(
                    "manudocs_users"
                )
            )
            user_column_lookup = {column["name"]: column for column in user_columns}
            assert user_column_lookup["organization_id"]["nullable"] is True
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
                (
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
                )
                .scalars()
                .all()
            )
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
            assert "manudocs_email_templates" not in tables
            assert "manudocs_email_tracks" not in tables

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
        f"postgresql+asyncpg://manudocsuser:manudocs@localhost:{host_port}/manudocsdb"
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
