import asyncio
from collections.abc import AsyncIterator
from typing import Any


class DemoEventBus:
    def __init__(self) -> None:
        self._sequence = 0
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

    def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        self._sequence += 1
        event = {"id": self._sequence, "type": event_type, "payload": payload}
        for queue in tuple(self._subscribers):
            queue.put_nowait(event)

    async def subscribe(self) -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers.add(queue)
        try:
            while True:
                try:
                    yield await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield {"id": self._sequence, "type": "heartbeat", "payload": {}}
        finally:
            self._subscribers.discard(queue)


demo_events = DemoEventBus()
