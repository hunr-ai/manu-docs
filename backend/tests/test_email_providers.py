import asyncio
from collections.abc import Coroutine
from typing import Any, TypeVar

import pytest
from config.settings.schemas import EmailProviderSettings
from emails.email_service import RenderedEmail
from emails.providers import console_email_provider, resend_email_provider
from emails.providers.base_provider import BaseEmailProvider
from emails.providers.console_email_provider import ConsoleEmailProvider
from emails.providers.provider_loader import load_email_provider
from emails.providers.resend_email_provider import ResendClient
from emails.providers.smtp_email_provider import SMTPEmailProvider
from pydantic import SecretStr

AsyncReturn = TypeVar("AsyncReturn")


class FakeLogger:
    def __init__(self):
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def ainfo(self, message: str, **kwargs: object) -> None:
        self.calls.append((message, kwargs))


def run_async(value: Coroutine[Any, Any, AsyncReturn]) -> AsyncReturn:
    return asyncio.run(value)


def make_rendered_email() -> RenderedEmail:
    return RenderedEmail(
        subject="Login code",
        html_body="<strong>123456</strong>",
        text_body="Your code is 123456.",
        to="user@example.test",
        from_email="sender@example.test",
    )


def test_base_email_provider_requires_subclass_implementation() -> None:
    provider = BaseEmailProvider()

    with pytest.raises(NotImplementedError, match="send_email must be implemented"):
        run_async(provider.send_email(make_rendered_email()))


def test_console_email_provider_logs_rendered_email(monkeypatch) -> None:
    logger = FakeLogger()
    monkeypatch.setattr(console_email_provider, "logger", logger)
    provider = ConsoleEmailProvider()
    rendered_email = make_rendered_email()

    sent = run_async(provider.send_email(rendered_email))

    assert sent is True
    assert logger.calls == [
        (
            "Sending email",
            {
                "subject": "Login code",
                "to": "user@example.test",
                "from_email": "sender@example.test",
                "html_body": "<strong>123456</strong>",
                "text_body": "Your code is 123456.",
            },
        ),
        ("Email sent successfully", {}),
    ]


@pytest.mark.parametrize(
    ("settings", "provider_type"),
    [
        (EmailProviderSettings(provider="console"), ConsoleEmailProvider),
        (
            EmailProviderSettings(
                provider="resend",
                resend_api_key=SecretStr("resend-secret"),
            ),
            ResendClient,
        ),
        (
            EmailProviderSettings(provider="smtp", smtp_host="smtp.example.test"),
            SMTPEmailProvider,
        ),
    ],
)
def test_load_email_provider_returns_configured_provider(
    settings: EmailProviderSettings,
    provider_type: type[BaseEmailProvider],
) -> None:
    provider = load_email_provider(settings)

    assert isinstance(provider, provider_type)


@pytest.mark.parametrize(
    ("settings", "match"),
    [
        (
            EmailProviderSettings(provider="resend"),
            "Resend API key must be provided",
        ),
        (
            EmailProviderSettings(
                provider="smtp",
                resend_api_key=SecretStr("resend-secret"),
            ),
            "provider must be set to 'resend'",
        ),
    ],
)
def test_resend_client_validates_required_settings(
    settings: EmailProviderSettings,
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        ResendClient(settings)


def test_resend_client_sends_rendered_email(monkeypatch) -> None:
    send_calls: list[dict[str, str]] = []

    class FakeEmails:
        @staticmethod
        def send(params: dict[str, str]) -> None:
            send_calls.append(params)

    monkeypatch.setattr(resend_email_provider.resend, "Emails", FakeEmails)

    provider = ResendClient(
        EmailProviderSettings(
            provider="resend",
            resend_api_key=SecretStr("resend-secret"),
        )
    )

    sent = run_async(provider.send_email(make_rendered_email()))

    assert sent is True
    assert resend_email_provider.resend.api_key == "resend-secret"
    assert send_calls == [
        {
            "from": "sender@example.test",
            "to": "user@example.test",
            "subject": "Login code",
            "html": "<strong>123456</strong>",
            "text": "Your code is 123456.",
        }
    ]


def test_resend_client_uses_default_addresses(monkeypatch) -> None:
    send_calls: list[dict[str, str]] = []

    class FakeEmails:
        @staticmethod
        def send(params: dict[str, str]) -> None:
            send_calls.append(params)

    monkeypatch.setattr(resend_email_provider.resend, "Emails", FakeEmails)
    provider = ResendClient(
        EmailProviderSettings(
            provider="resend",
            resend_api_key=SecretStr("resend-secret"),
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

    assert send_calls == [
        {
            "from": "DoNotReply@manudocs.hunr.ai",
            "to": "",
            "subject": "Subject",
            "html": "<p>Hello</p>",
            "text": "Hello",
        }
    ]
