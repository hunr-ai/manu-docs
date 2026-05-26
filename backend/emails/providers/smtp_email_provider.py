import asyncio
import smtplib
from email.message import EmailMessage

from config.settings.schemas import EmailProviderSettings
from emails.email_service import RenderedEmail

from .base_provider import BaseEmailProvider


class SMTPEmailProvider(BaseEmailProvider):
    def __init__(self, settings: EmailProviderSettings):
        self._settings = settings
        if settings.provider != "smtp":
            raise ValueError(
                "Email provider must be set to 'smtp' for SMTPEmailProvider"
            )
        if not settings.smtp_host:
            raise ValueError("SMTP host must be provided for SMTP email provider")
        if settings.smtp_password and not settings.smtp_username:
            raise ValueError("SMTP username must be provided when SMTP password is set")
        self._host = settings.smtp_host

    async def send_email(self, rendered_email: RenderedEmail) -> bool:
        message = self._build_message(rendered_email)
        await asyncio.to_thread(self._send_message, message)
        return True

    def _build_message(self, rendered_email: RenderedEmail) -> EmailMessage:
        message = EmailMessage()
        message["Subject"] = rendered_email.subject
        message["From"] = rendered_email.from_email or "DoNotReply@manudocs.hunr.ai"
        message["To"] = rendered_email.to or ""
        message.set_content(rendered_email.text_body)
        message.add_alternative(rendered_email.html_body, subtype="html")
        return message

    def _send_message(self, message: EmailMessage) -> None:
        with smtplib.SMTP(self._host, self._settings.smtp_port) as smtp:
            if self._settings.smtp_use_tls:
                smtp.starttls()
            if self._settings.smtp_username:
                password = (
                    self._settings.smtp_password.get_secret_value()
                    if self._settings.smtp_password
                    else ""
                )
                smtp.login(self._settings.smtp_username, password)
            smtp.send_message(message)
