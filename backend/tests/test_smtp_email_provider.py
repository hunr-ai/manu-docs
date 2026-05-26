import asyncio
from collections.abc import Coroutine
from email.message import EmailMessage
from typing import Any, TypeVar

import pytest
from config.settings.schemas import EmailProviderSettings
from emails.email_service import RenderedEmail
from emails.providers import smtp_email_provider
from emails.providers.smtp_email_provider import SMTPEmailProvider
from pydantic import SecretStr

AsyncReturn = TypeVar("AsyncReturn")


class FakeSMTP:
    instances: list["FakeSMTP"] = []

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.started_tls = False
        self.login_calls: list[tuple[str, str]] = []
        self.sent_messages: list[EmailMessage] = []
        self.closed = False
        self.__class__.instances.append(self)

    def __enter__(self) -> "FakeSMTP":
        return self

    def __exit__(self, *args: object) -> None:
        self.closed = True

    def starttls(self) -> None:
        self.started_tls = True

    def login(self, username: str, password: str) -> None:
        self.login_calls.append((username, password))

    def send_message(self, message: EmailMessage) -> None:
        self.sent_messages.append(message)


def run_async(value: Coroutine[Any, Any, AsyncReturn]) -> AsyncReturn:
    return asyncio.run(value)


@pytest.fixture(autouse=True)
def clear_fake_smtp() -> None:
    FakeSMTP.instances.clear()


def test_smtp_provider_sends_multipart_email(monkeypatch) -> None:
    monkeypatch.setattr(smtp_email_provider.smtplib, "SMTP", FakeSMTP)
    provider = SMTPEmailProvider(
        EmailProviderSettings(
            provider="smtp",
            smtp_host="smtp.example.test",
            smtp_port=2525,
            smtp_username="smtp-user",
            smtp_password=SecretStr("smtp-secret"),
        )
    )
    rendered_email = RenderedEmail(
        subject="Login code",
        html_body="<strong>123456</strong>",
        text_body="Your code is 123456.",
        to="user@example.test",
        from_email="sender@example.test",
    )

    sent = run_async(provider.send_email(rendered_email))

    assert sent is True
    smtp = FakeSMTP.instances[0]
    assert smtp.host == "smtp.example.test"
    assert smtp.port == 2525
    assert smtp.started_tls is True
    assert smtp.login_calls == [("smtp-user", "smtp-secret")]
    assert smtp.closed is True
    message = smtp.sent_messages[0]
    assert message["Subject"] == "Login code"
    assert message["From"] == "sender@example.test"
    assert message["To"] == "user@example.test"
    assert message.get_body(("plain",)).get_content() == "Your code is 123456.\n"
    assert message.get_body(("html",)).get_content() == "<strong>123456</strong>\n"


def test_smtp_provider_skips_tls_and_auth_when_disabled(monkeypatch) -> None:
    monkeypatch.setattr(smtp_email_provider.smtplib, "SMTP", FakeSMTP)
    provider = SMTPEmailProvider(
        EmailProviderSettings(
            provider="smtp",
            smtp_host="smtp.example.test",
            smtp_use_tls=False,
        )
    )

    run_async(
        provider.send_email(
            RenderedEmail(
                subject="Subject",
                html_body="<p>Hello</p>",
                text_body="Hello",
            )
        )
    )

    smtp = FakeSMTP.instances[0]
    assert smtp.started_tls is False
    assert smtp.login_calls == []
    message = smtp.sent_messages[0]
    assert message["From"] == "DoNotReply@manudocs.hunr.ai"
    assert message["To"] == ""


@pytest.mark.parametrize(
    ("settings", "match"),
    [
        (
            EmailProviderSettings(provider="resend", smtp_host="smtp.example.test"),
            "provider must be set to 'smtp'",
        ),
        (EmailProviderSettings(provider="smtp"), "SMTP host must be provided"),
        (
            EmailProviderSettings(
                provider="smtp",
                smtp_host="smtp.example.test",
                smtp_password=SecretStr("smtp-secret"),
            ),
            "SMTP username must be provided",
        ),
    ],
)
def test_smtp_provider_validates_required_settings(
    settings: EmailProviderSettings, match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        SMTPEmailProvider(settings)
