import asyncio
from collections.abc import AsyncGenerator, Coroutine
from typing import Any, TypeVar, cast

import pytest
from db.get_session import get_db_session

AsyncReturn = TypeVar("AsyncReturn")


class FakeSession:
    def __init__(self):
        self.closed = False
        self.rolled_back = False

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *args: object) -> None:
        self.closed = True

    async def rollback(self) -> None:
        self.rolled_back = True


class FakeSessionmaker:
    def __init__(self, session: FakeSession):
        self.session = session
        self.calls = 0

    def __call__(self) -> FakeSession:
        self.calls += 1
        return self.session


class FakeState:
    def __init__(self, sessionmaker: FakeSessionmaker):
        self.db_sessionmaker = sessionmaker


class FakeApp:
    def __init__(self, sessionmaker: FakeSessionmaker):
        self.state = FakeState(sessionmaker)


class FakeRequest:
    def __init__(self, sessionmaker: FakeSessionmaker):
        self.app = FakeApp(sessionmaker)


def run_async(value: Coroutine[Any, Any, AsyncReturn]) -> AsyncReturn:
    return asyncio.run(value)


def make_session_generator(
    request: FakeRequest,
) -> AsyncGenerator[FakeSession, None]:
    return cast(AsyncGenerator[FakeSession, None], get_db_session(cast(Any, request)))


def test_get_db_session_yields_request_scoped_session() -> None:
    session = FakeSession()
    sessionmaker = FakeSessionmaker(session)
    request = FakeRequest(sessionmaker)
    session_generator = make_session_generator(request)

    yielded_session = run_async(anext(session_generator))
    run_async(session_generator.aclose())

    assert yielded_session is session
    assert sessionmaker.calls == 1
    assert session.closed is True
    assert session.rolled_back is False


def test_get_db_session_rolls_back_when_consumer_raises() -> None:
    session = FakeSession()
    sessionmaker = FakeSessionmaker(session)
    request = FakeRequest(sessionmaker)
    session_generator = make_session_generator(request)

    assert run_async(anext(session_generator)) is session
    with pytest.raises(RuntimeError, match="boom"):
        run_async(session_generator.athrow(RuntimeError("boom")))

    assert sessionmaker.calls == 1
    assert session.closed is True
    assert session.rolled_back is True
