"""Per-run event stream: events are stored (for replay) and pushed to live listeners."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from .store import store


class RunChannel:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.seq = -1
        self.listeners: set[asyncio.Queue] = set()
        self.closed = False
        self._lock = asyncio.Lock()
        # Batching for high-volume events (one reaction per agent).
        self._buffer: dict[str, list[Any]] = {}
        self._last_flush = time.monotonic()

    async def emit(self, etype: str, data: Any) -> None:
        async with self._lock:
            self.seq += 1
            seq = self.seq
            await store.add_event(self.run_id, seq, etype, data)
        evt = {"seq": seq, "ts": time.time(), "type": etype, "data": data}
        for q in list(self.listeners):
            q.put_nowait(evt)

    async def buffered(self, etype: str, item: Any, every: float = 0.4) -> None:
        self._buffer.setdefault(etype, []).append(item)
        if time.monotonic() - self._last_flush >= every:
            await self.flush()

    async def flush(self) -> None:
        self._last_flush = time.monotonic()
        buf, self._buffer = self._buffer, {}
        for etype, items in buf.items():
            if items:
                await self.emit(etype, items)

    async def close(self) -> None:
        await self.flush()
        self.closed = True
        for q in list(self.listeners):
            q.put_nowait(None)


class Hub:
    def __init__(self) -> None:
        self.channels: dict[str, RunChannel] = {}

    def open(self, run_id: str) -> RunChannel:
        ch = RunChannel(run_id)
        self.channels[run_id] = ch
        return ch

    def get(self, run_id: str) -> RunChannel | None:
        return self.channels.get(run_id)

    def drop(self, run_id: str) -> None:
        self.channels.pop(run_id, None)


hub = Hub()
