import asyncio
import json
import logging
from typing import Any, Set

logger = logging.getLogger("events")

class EventBroadcaster:
    def __init__(self):
        self._subscribers: Set[asyncio.Queue] = set()

    def subscribe(self, maxsize: int = 100) -> asyncio.Queue:
        q = asyncio.Queue(maxsize=maxsize)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        if q in self._subscribers:
            self._subscribers.remove(q)

    async def broadcast(self, event_type: str, data: Any):
        if not self._subscribers:
            return
        event_dict = {"event": event_type, "data": data}
        for q in list(self._subscribers):
            try:
                if q.full():
                    try:
                        q.get_nowait()  # Drop oldest event if subscriber is slow
                    except asyncio.QueueEmpty:
                        pass
                q.put_nowait(event_dict)
            except Exception as e:
                logger.debug(f"Failed to put event into queue: {e}")

broadcaster = EventBroadcaster()
