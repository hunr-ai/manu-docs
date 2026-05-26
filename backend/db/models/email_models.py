import datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column

from .base_model import BaseModel


class EmailTemplate(BaseModel):
    __tablename__ = "manudocs_email_templates"

    name: Mapped[str] = mapped_column(unique=True, nullable=False)
    use_case: Mapped[str] = mapped_column(unique=True, nullable=False)
    subject: Mapped[str] = mapped_column(nullable=False)
    html_template: Mapped[str] = mapped_column(nullable=False)
    text_template: Mapped[str] = mapped_column(nullable=False)


class EmailTrack(BaseModel):
    __tablename__ = "manudocs_email_tracks"

    recipient: Mapped[str] = mapped_column(nullable=False)
    subject: Mapped[str] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(
        nullable=False,
        default="pending",
        server_default="pending",
    )
    tracking_token: Mapped[str] = mapped_column(
        unique=True,
        index=True,
        nullable=False,
    )
    sent_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    read_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(nullable=True)
