from dataclasses import dataclass

from db.models import EmailTemplate
from jinja2 import StrictUndefined, Template
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    html_body: str
    text_body: str
    to: str | None = None
    from_email: str | None = None


class EmailService:
    def __init__(self, db_session: AsyncSession):
        self._db_session = db_session

    async def get_email_template(self, use_case: str) -> EmailTemplate:
        result = await self._db_session.execute(
            select(EmailTemplate).where(EmailTemplate.use_case == use_case)
        )
        return result.scalar_one()

    async def render_login_email(self, email: str, otp: str) -> RenderedEmail:
        template = await self.get_email_template("login")
        context = {"email": email, "otp": otp}
        rendered_email = RenderedEmail(
            subject=self._render_template(template.subject, context),
            html_body=self._render_template(template.html_template, context),
            text_body=self._render_template(template.text_template, context),
            from_email="DoNotReply@manudocs.hunr.ai",
            to=email,
        )
        return rendered_email

    def _render_template(self, source: str, context: dict[str, str]) -> str:
        return Template(source, undefined=StrictUndefined).render(context)

    def render_tracking_pixel(self, tracking_url: str) -> str:
        return (
            f'<img src="{tracking_url}" alt="" width="1" height="1" '
            'style="display:none;width:1px;height:1px" />'
        )
