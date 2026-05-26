import resend
from config.settings.schemas import EmailProviderSettings
from emails.email_service import RenderedEmail

from .base_provider import BaseEmailProvider


class ResendClient(BaseEmailProvider):
    def __init__(self, settings: EmailProviderSettings):
        self._settings = settings
        if not settings.resend_api_key:
            raise ValueError(
                "Resend API key must be provided for Resend email provider"
            )
        if not settings.provider == "resend":
            raise ValueError("Email provider must be set to 'resend' for ResendClient")
        self._api_key = settings.resend_api_key.get_secret_value()
        resend.api_key = self._api_key

    async def send_email(self, rendered_email: RenderedEmail) -> bool:
        params: resend.Emails.SendParams = {
            "from": rendered_email.from_email or "DoNotReply@manudocs.hunr.ai",
            "to": rendered_email.to or "",
            "subject": rendered_email.subject,
            "html": rendered_email.html_body,
            "text": rendered_email.text_body,
        }
        resend.Emails.send(params)
        return True
