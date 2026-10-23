"""Small infrastructure input contracts used by application operations."""

from typing import Protocol
from functools import partial
from anyio import to_thread


class UploadedFile(Protocol):
    filename: str | None
    content_type: str | None

    async def read(self, size: int = -1) -> bytes: ...


async def run_in_threadpool(function, *args, **kwargs):
    return await to_thread.run_sync(partial(function, *args, **kwargs))
