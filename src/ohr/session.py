"""Request/response correlation over a connection.

Pure: this module knows nothing about sockets or platforms. It takes anything
satisfying :class:`ohr.transport.Connection` and applies the two framing rules that are
easy to get wrong, once, so consumers do not each re-implement them:

* **A read is not a frame.** Reads are buffered and reassembled.
* **Replies correlate by feature and operation, never by arrival order.** Notifications
  can arrive between a request and its response.

Unsolicited frames are not discarded; they are queued and can be drained with
:meth:`Session.take_events`.
"""

from __future__ import annotations

import time
from collections.abc import Iterator

from .errors import ReplyTimeout
from .frame import Frame, FrameStream
from .transport import Connection


class Session:
    """Issues requests on a connection and matches up the replies."""

    __slots__ = ("_conn", "_stream", "_events")

    def __init__(self, connection: Connection) -> None:
        self._conn = connection
        self._stream = FrameStream()
        self._events: list[Frame] = []

    def request(self, frame: Frame, *, timeout: float = 5.0) -> Frame:
        """Send ``frame`` and return its reply.

        The reply may be an :attr:`MessageType.ERROR` frame — that is an answer, not a
        transport failure, and it means *state unknown*, so the caller should re-read
        rather than assume the command failed.

        Raises :class:`ohr.errors.ReplyTimeout` if nothing matching arrives in time.
        """
        self._conn.send(frame.to_bytes(), timeout=timeout)
        deadline = time.monotonic() + timeout

        for reply in self._drain_queued(frame):
            return reply

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                chunk = self._conn.receive(timeout=remaining)
            except TimeoutError:
                # A quiet transport is not an answer. Keep waiting until our own
                # deadline, then report it as ours rather than leaking the socket's.
                continue
            for received in self._stream.feed(chunk):
                if received.matches_reply_to(frame):
                    return received
                self._events.append(received)

        raise ReplyTimeout(
            f"no reply to feature {frame.feature} operation {frame.operation} "
            f"within {timeout}s"
        )

    def _drain_queued(self, frame: Frame) -> Iterator[Frame]:
        """Yield an already-queued reply, if one is waiting from an earlier read."""
        for index, queued in enumerate(self._events):
            if queued.matches_reply_to(frame):
                del self._events[index]
                yield queued
                return

    def take_events(self) -> list[Frame]:
        """Remove and return every unsolicited frame received so far.

        Notifications are only delivered after a subscription, which mutates session
        state; without one this is normally empty.
        """
        events, self._events = self._events, []
        return events

    @property
    def pending_events(self) -> int:
        return len(self._events)
