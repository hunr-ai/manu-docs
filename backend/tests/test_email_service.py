import asyncio
from collections.abc import Coroutine
from typing import Any, TypeVar, cast

import pytest
from db.models import EmailTemplate
from emails.email_service import EmailService, RenderedEmail
from jinja2 import UndefinedError
from sqlalchemy.ext.asyncio import AsyncSession

AsyncReturn = TypeVar("AsyncReturn")


class FakeResult:
    def __init__(self, template: EmailTemplate):
        self._template = template

    def scalar_one(self) -> EmailTemplate:
        return self._template


class FakeSession:
    def __init__(self, template: EmailTemplate):
        self.template = template
        self.statements: list[object] = []

    async def execute(self, statement: object) -> FakeResult:
        self.statements.append(statement)
        return FakeResult(self.template)


def run_async(value: Coroutine[Any, Any, AsyncReturn]) -> AsyncReturn:
    return asyncio.run(value)


def test_render_login_email_renders_jinja_subject_html_and_text() -> None:
    template = EmailTemplate(
        name="Login code",
        use_case="login",
        subject="Code for {{ email }}",
        html_template="<strong>{{ otp }}</strong>",
        text_template="Your code is {{ otp }}.",
    )
    service = EmailService(cast(AsyncSession, FakeSession(template)))

    rendered = run_async(service.render_login_email("user@example.test", "123456"))

    assert rendered == RenderedEmail(
        subject="Code for user@example.test",
        html_body="<strong>123456</strong>",
        text_body="Your code is 123456.",
        to="user@example.test",
        from_email="DoNotReply@manudocs.hunr.ai",
    )


def test_render_login_email_fails_on_missing_template_variable() -> None:
    template = EmailTemplate(
        name="Login code",
        use_case="login",
        subject="{{ missing }}",
        html_template="{{ otp }}",
        text_template="{{ otp }}",
    )
    service = EmailService(cast(AsyncSession, FakeSession(template)))

    with pytest.raises(UndefinedError):
        run_async(service.render_login_email("user@example.test", "123456"))


def test_render_tracking_pixel_returns_hidden_image_tag() -> None:
    template = EmailTemplate(
        name="Login code",
        use_case="login",
        subject="subject",
        html_template="html",
        text_template="text",
    )
    service = EmailService(cast(AsyncSession, FakeSession(template)))

    rendered = service.render_tracking_pixel("/emails/tracking/token.png")

    assert rendered == (
        '<img src="/emails/tracking/token.png" alt="" width="1" height="1" '
        'style="display:none;width:1px;height:1px" />'
    )
