from enum import Enum

from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base_model import BaseModel


class UserRole(Enum):
    ADMIN = "admin"
    OWNER = "owner"
    VIEWER = "viewer"
    MEMBER = "member"


class Organization(BaseModel):
    __tablename__ = "manudocs_organizations"

    name: Mapped[str] = mapped_column(unique=True, nullable=False)

    users: Mapped[list["User"]] = relationship(
        back_populates="organization",
        passive_deletes=True,
    )


class User(BaseModel):
    __tablename__ = "manudocs_users"
    __table_args__ = (
        Index("ix_manudocs_users_organization_id_role", "organization_id", "role"),
    )

    email: Mapped[str] = mapped_column(unique=True, nullable=False)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("manudocs_organizations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[UserRole] = mapped_column(
        SQLEnum(UserRole, name="manudocs_user_role"), nullable=False
    )

    organization: Mapped["Organization"] = relationship(back_populates="users")
