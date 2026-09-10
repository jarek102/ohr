"""Session correlation, against a fake connection.

No sockets and no hardware: the point of keeping :mod:`ohr.session` pure is that its
awkward cases — a reply split across reads, a notification arriving mid-exchange — can
be provoked deterministically instead of waited for.
"""

from __future__ import annotations

import pytest

from ohr import Frame, MessageType
from ohr.errors import ReplyTimeout
from ohr.session import Session

VENDOR = 0x0495


def frame(feature: int, kind: MessageType, operation: int, payload: bytes = b"") -> Frame:
    return Frame(VENDOR, feature, kind, operation, payload)


class FakeConnection:
    """Replays a scripted sequence of reads, recording what was sent."""

    def __init__(self, reads: list[bytes]) -> None:
        self.reads = list(reads)
        self.sent: list[bytes] = []

    def send(self, data: bytes, *, timeout: float) -> None:
        self.sent.append(data)

    def receive(self, *, timeout: float) -> bytes:
        if not self.reads:
            raise TimeoutError("no more scripted reads")
        return self.reads.pop(0)

    def close(self) -> None:
        pass


REQUEST = frame(3, MessageType.COMMAND, 3)
RESPONSE = frame(3, MessageType.RESPONSE, 3, b"\x46")


def test_sends_the_request_bytes() -> None:
    conn = FakeConnection([RESPONSE.to_bytes()])
    Session(conn).request(REQUEST)
    assert conn.sent == [REQUEST.to_bytes()]


def test_reply_split_across_reads() -> None:
    raw = RESPONSE.to_bytes()
    conn = FakeConnection([raw[:5], raw[5:]])
    assert Session(conn).request(REQUEST).payload == b"\x46"


def test_notification_between_request_and_response_is_not_mistaken_for_it() -> None:
    """Correlation is by feature and operation, never by arrival order."""
    notification = frame(3, MessageType.NOTIFICATION, 3, b"\x01\x02\x03")
    conn = FakeConnection([notification.to_bytes() + RESPONSE.to_bytes()])
    session = Session(conn)

    assert session.request(REQUEST).payload == b"\x46"

    events = session.take_events()
    assert [e.type for e in events] == [MessageType.NOTIFICATION]
    assert session.take_events() == [], "events should be drained once taken"


def test_unrelated_response_does_not_satisfy_the_request() -> None:
    other = frame(8, MessageType.RESPONSE, 9, b"\xff")
    conn = FakeConnection([other.to_bytes(), RESPONSE.to_bytes()])
    session = Session(conn)
    assert session.request(REQUEST).payload == b"\x46"
    assert [e.feature for e in session.take_events()] == [8]


def test_error_reply_is_returned_not_raised() -> None:
    """An error is an answer. It means state unknown, not failure to send."""
    error = frame(3, MessageType.ERROR, 3, b"\x05")
    conn = FakeConnection([error.to_bytes()])
    reply = Session(conn).request(REQUEST)
    assert reply.type is MessageType.ERROR
    assert reply.payload == b"\x05"


def test_queued_reply_from_an_earlier_read_is_used() -> None:
    """A reply that arrived early must not be dropped or waited for twice."""
    second = frame(8, MessageType.COMMAND, 9)
    early = frame(8, MessageType.RESPONSE, 9, b"\x01")
    conn = FakeConnection([early.to_bytes() + RESPONSE.to_bytes()])
    session = Session(conn)

    assert session.request(REQUEST).payload == b"\x46"
    assert session.pending_events == 1
    assert session.request(second, timeout=0.1).payload == b"\x01"
    assert session.pending_events == 0


def test_timeout_when_nothing_matches() -> None:
    conn = FakeConnection([])
    with pytest.raises(ReplyTimeout):
        Session(conn).request(REQUEST, timeout=0.05)
