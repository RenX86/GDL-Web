"""Session-scoped Server-Sent Events (SSE) publish/subscribe broker."""

from __future__ import annotations

import asyncio
from typing import Any

from app.exceptions import QuotaExceededError


class SessionBroker:
    """In-memory session-keyed pub/sub fan-out with per-session connection caps."""

    def __init__(
        self,
        max_connections_per_session: int = 5,
        queue_maxsize: int = 100,
    ) -> None:
        self._max_connections = max_connections_per_session
        self._queue_maxsize = queue_maxsize
        self._channels: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}

    def subscribe(self, session_id: str) -> asyncio.Queue[dict[str, Any]]:
        """Register a new SSE subscriber queue for the given session."""
        queues = self._channels.setdefault(session_id, set())
        if len(queues) >= self._max_connections:
            raise QuotaExceededError(
                "Maximum concurrent live event connections reached for this session."
            )
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(
            maxsize=self._queue_maxsize
        )
        queues.add(queue)
        return queue

    def unsubscribe(
        self, session_id: str, queue: asyncio.Queue[dict[str, Any]]
    ) -> None:
        """Remove a subscriber queue and prune empty session buckets."""
        queues = self._channels.get(session_id)
        if not queues:
            return
        queues.discard(queue)
        if not queues:
            self._channels.pop(session_id, None)

    def publish(self, session_id: str, event_type: str, data: Any) -> None:
        """Deliver an event only to subscribers belonging to session_id."""
        queues = self._channels.get(session_id)
        if not queues:
            return

        payload = {"event": event_type, "data": data}
        for queue in list(queues):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                pass

    def close_session(self, session_id: str) -> None:
        """Drop all subscriber queues for a cleared session."""
        self._channels.pop(session_id, None)

    def subscriber_count(self, session_id: str) -> int:
        """Return active SSE subscriber count for a session."""
        return len(self._channels.get(session_id, set()))
