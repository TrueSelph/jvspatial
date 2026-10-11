"""Streaming must yield before EOF and close when its consumer stops."""

import io
from types import SimpleNamespace

import pytest

from jvspatial.storage.interfaces.local import LocalFileInterface
from jvspatial.storage.interfaces.s3 import S3FileInterface


class TrackingBody(io.BytesIO):
    def __init__(self):
        super().__init__(b"x" * 1024)
        self.reads = 0

    def read(self, size=-1):
        self.reads += 1
        return super().read(size)


class StubS3(S3FileInterface):
    def __init__(self, body):
        self.bucket_name = "stub"
        self.s3_client = SimpleNamespace(get_object=lambda **kw: {"Body": body})
        self._ClientError = RuntimeError

    def _sanitize_key(self, path):
        return path


@pytest.mark.parametrize("provider", ["local", "s3"])
async def test_stream_has_backpressure_and_closes(provider, monkeypatch, tmp_path):
    body = TrackingBody()
    if provider == "local":
        path = tmp_path / "file.txt"
        path.write_bytes(b"x" * 1024)
        storage = LocalFileInterface(root_dir=str(tmp_path))
        monkeypatch.setattr("builtins.open", lambda *args, **kw: body)
    else:
        storage = StubS3(body)
    stream = storage.stream_file("file.txt", chunk_size=64)
    assert await anext(stream) == b"x" * 64
    assert body.reads == 1
    assert not body.closed
    await stream.aclose()
    assert body.closed


async def test_cancellation_waits_for_read_then_closes():
    import asyncio
    import threading

    from jvspatial.storage.interfaces._stream import stream_reader

    entered, release = threading.Event(), threading.Event()

    class BlockingBody(TrackingBody):
        def read(self, size=-1):
            entered.set()
            assert release.wait(3)
            assert not self.closed
            return super().read(size)

    body = BlockingBody()
    stream = stream_reader(lambda: body, 64)
    task = asyncio.create_task(anext(stream))
    assert await asyncio.to_thread(entered.wait, 3)
    task.cancel()
    await asyncio.sleep(0.01)
    assert not body.closed
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert body.closed


@pytest.mark.parametrize("phase", ["open", "read", "close"])
async def test_repeated_cancellation_drains_worker_before_cleanup(phase):
    import asyncio
    import threading

    from jvspatial.storage.interfaces._stream import stream_reader

    entered, release = threading.Event(), threading.Event()

    def block():
        entered.set()
        assert release.wait(3)

    class BlockingBody(TrackingBody):
        def read(self, size=-1):
            if phase == "read":
                block()
                assert not self.closed
            return b"" if phase == "close" else super().read(size)

        def close(self):
            if phase == "close":
                block()
            super().close()

    body = BlockingBody()

    def open_reader():
        if phase == "open":
            block()
        return body

    task = asyncio.create_task(anext(stream_reader(open_reader, 64)))
    try:
        assert await asyncio.to_thread(entered.wait, 3)
        task.cancel()
        await asyncio.sleep(0.01)
        task.cancel()
        await asyncio.sleep(0.01)
        assert not body.closed
        assert not task.done()
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert body.closed


@pytest.mark.parametrize("size", [0, -1, True, 1.5])
async def test_invalid_chunk_size_never_opens_reader(size):
    from jvspatial.storage.interfaces._stream import stream_reader

    opened = False

    def opener():
        nonlocal opened
        opened = True
        return TrackingBody()

    with pytest.raises(ValueError, match="positive integer"):
        await anext(stream_reader(opener, size))
    assert not opened
