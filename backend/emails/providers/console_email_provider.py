from emails.email_service import RenderedEmail
from emails.providers.base_provider import BaseEmailProvider
from structlog import get_logger

logger = get_logger(__name__)


class ConsoleEmailProvider(BaseEmailProvider):
    async def send_email(self, rendered_email: RenderedEmail) -> bool:
        await logger.ainfo(
            "Sending email",
            subject=rendered_email.subject,
            to=rendered_email.to,
            from_email=rendered_email.from_email,
            html_body=rendered_email.html_body,
            text_body=rendered_email.text_body,
        )
        await logger.ainfo("Email sent successfully")
        return True
