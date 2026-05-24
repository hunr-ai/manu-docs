from typing import cast

import db.models.docs_model
from db.models import BaseModel, Organization, User, UserRole
from sqlalchemy import DefaultClause, Table
from sqlalchemy import Enum as SqlAlchemyEnum


def test_models_are_registered_in_base_metadata() -> None:
    assert set(BaseModel.metadata.tables) == {
        "manudocs_organizations",
        "manudocs_users",
    }


def test_organization_table_shape() -> None:
    table = cast(Table, Organization.__table__)

    assert table.name == "manudocs_organizations"
    assert set(table.c.keys()) == {"name", "id", "created_at", "updated_at"}
    assert table.c.id.primary_key is True
    assert table.c.id.autoincrement is True
    assert table.c.name.nullable is False
    assert table.c.name.unique is True
    created_at_default = cast(DefaultClause, table.c.created_at.server_default)
    updated_at_default = cast(DefaultClause, table.c.updated_at.server_default)
    assert str(created_at_default.arg) == "now()"
    assert str(updated_at_default.arg) == "now()"


def test_user_table_shape() -> None:
    table = cast(Table, User.__table__)
    role_type = cast(SqlAlchemyEnum, table.c.role.type)

    assert table.name == "manudocs_users"
    assert set(table.c.keys()) == {
        "email",
        "organization_id",
        "role",
        "id",
        "created_at",
        "updated_at",
    }
    assert table.c.email.nullable is False
    assert table.c.email.unique is True
    assert table.c.organization_id.nullable is False
    assert table.c.role.nullable is False
    assert role_type.name == "manudocs_user_role"
    assert role_type.enums == ["ADMIN", "OWNER", "VIEWER", "MEMBER"]


def test_user_foreign_key_cascades_on_organization_delete() -> None:
    table = cast(Table, User.__table__)
    foreign_key = next(iter(table.c.organization_id.foreign_keys))

    assert foreign_key.target_fullname == "manudocs_organizations.id"
    assert foreign_key.ondelete == "CASCADE"


def test_user_index_matches_query_pattern() -> None:
    table = cast(Table, User.__table__)
    indexes = {str(index.name): index for index in table.indexes}
    index = indexes["ix_manudocs_users_organization_id_role"]

    assert [column.name for column in index.columns] == ["organization_id", "role"]
    assert index.unique is False


def test_relationships_are_bidirectional() -> None:
    assert Organization.users.property.back_populates == "organization"
    assert Organization.users.property.passive_deletes is True
    assert User.organization.property.back_populates == "users"


def test_user_role_values_match_public_contract() -> None:
    assert {role.name: role.value for role in UserRole} == {
        "ADMIN": "admin",
        "OWNER": "owner",
        "VIEWER": "viewer",
        "MEMBER": "member",
    }


def test_docs_model_module_is_importable() -> None:
    assert db.models.docs_model is not None
