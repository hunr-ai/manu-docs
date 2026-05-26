from config.settings.schemas import EmailProviderSettings

from .base_provider import BaseEmailProvider
from .console_email_provider import ConsoleEmailProvider
from .resend_email_provider import ResendClient
from .smtp_email_provider import SMTPEmailProvider


def load_email_provider(settings: EmailProviderSettings) -> BaseEmailProvider:
    if settings.provider == "console":
        return ConsoleEmailProvider()
    if settings.provider == "resend":
        return ResendClient(settings)
    if settings.provider == "smtp":
        return SMTPEmailProvider(settings)
    raise ValueError(f"Unsupported email provider: {settings.provider}")
