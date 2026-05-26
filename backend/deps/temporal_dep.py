from typing import cast

from fastapi import Request
from temporalio.client import Client


async def get_temporal_client(request: Request) -> Client:
    return cast(Client, request.app.state.temporal_client)
