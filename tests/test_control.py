"""The write path, against a scripted device.

Every case here is one an implementation gets wrong by being optimistic. They are worth
provoking offline, because the failure they guard against — reporting a change that
never happened — is silent on real hardware: the acknowledgement looks identical either
way.
"""

from __future__ import annotations

from ohr import Frame, MessageType, anc, control
from ohr.session import Session
from test_session import FakeConnection  # same directory; see pyproject's pythonpath

VENDOR = 0x0495

ACK = Frame(VENDOR, 13, MessageType.RESPONSE, anc.OP_SET_ENABLED)
ACK_TRANSPARENCY = Frame(VENDOR, 12, MessageType.RESPONSE, anc.OP_SET_ENABLED)


def reads_anc(value: int) -> bytes:
    return Frame(VENDOR, 13, MessageType.RESPONSE, anc.OP_ENABLED, bytes([value])).to_bytes()


def reads_transparency(value: int) -> bytes:
    return Frame(VENDOR, 12, MessageType.RESPONSE, anc.OP_ENABLED, bytes([value])).to_bytes()


def quick(conn: FakeConnection, steps) -> control.Applied:
    # No settle delay: the fake answers immediately, so a wait would only slow tests.
    return control.apply(Session(conn), steps, timeout=0.2, interval=0.0)


ANC_ON = anc.plan_mode(anc.Mode.ANC, anc.State(anc=False, transparency=False))


def test_write_confirmed_by_read_back() -> None:
    conn = FakeConnection([ACK.to_bytes(), reads_anc(1)])
    result = quick(conn, ANC_ON)

    assert result.complete
    assert result.outcomes[0].observed is True
    assert conn.sent == [
        anc.request_set_enabled(True).to_bytes(),
        anc.request_enabled().to_bytes(),
    ], "a write must be followed by its own read, not merely sent"


def test_acknowledged_but_unchanged_is_a_failure() -> None:
    """The case this module exists for: the device says yes and does nothing."""
    conn = FakeConnection([ACK.to_bytes(), reads_anc(0), reads_anc(0), reads_anc(0)])
    result = quick(conn, ANC_ON)

    assert not result.complete
    failed = result.failed
    assert failed is not None
    assert failed.acknowledged, "the write itself was accepted"
    assert failed.observed is False
    assert "still reports" in failed.describe()


def test_read_back_is_retried_but_the_write_is_not() -> None:
    """A change can lag its acknowledgement. Re-sending a setter that did take would
    apply it twice; re-reading costs nothing."""
    conn = FakeConnection([ACK.to_bytes(), reads_anc(0), reads_anc(1)])
    result = quick(conn, ANC_ON)

    assert result.complete
    assert conn.sent.count(anc.request_set_enabled(True).to_bytes()) == 1
    assert conn.sent.count(anc.request_enabled().to_bytes()) == 2


def test_sequence_stops_at_the_first_failure() -> None:
    """A half-applied mode must not be driven further into a state nobody chose."""
    plan = anc.plan_mode(anc.Mode.OFF, anc.State(anc=True, transparency=True))
    assert len(plan) == 2

    # The first write is acknowledged, but ANC stays on.
    conn = FakeConnection(
        [ACK.to_bytes(), reads_anc(1), reads_anc(1), reads_anc(1)]
    )
    result = quick(conn, plan)

    assert not result.complete
    assert len(result.outcomes) == 1, "the second step must not run"
    assert anc.request_set_transparency(False).to_bytes() not in conn.sent


def test_error_reply_still_reads_the_state_back() -> None:
    """A rejected write leaves the setting unknown, not unchanged — so read it."""
    rejected = Frame(VENDOR, 13, MessageType.ERROR, anc.OP_SET_ENABLED, b"\x05")
    conn = FakeConnection([rejected.to_bytes(), reads_anc(0)])
    result = quick(conn, ANC_ON)

    assert not result.complete
    outcome = result.outcomes[0]
    assert not outcome.acknowledged
    assert outcome.observed is False, "the caller needs the state, not just the verdict"


def test_unreadable_reply_is_reported_not_assumed() -> None:
    unreadable = Frame(VENDOR, 13, MessageType.RESPONSE, anc.OP_ENABLED, b"\x07")
    conn = FakeConnection([ACK.to_bytes(), *[unreadable.to_bytes()] * 3])
    result = quick(conn, ANC_ON)

    assert not result.complete
    assert "did not decode" in result.outcomes[0].describe()


def test_two_step_sequence_verifies_each_step_on_its_own_feature() -> None:
    """ANC and transparency are different features; verifying one proves nothing about
    the other."""
    plan = anc.plan_mode(anc.Mode.ANC, anc.State(anc=False, transparency=True))
    conn = FakeConnection(
        [ACK_TRANSPARENCY.to_bytes(), reads_transparency(0), ACK.to_bytes(), reads_anc(1)]
    )
    result = quick(conn, plan)

    assert result.complete
    assert conn.sent == [
        anc.request_set_transparency(False).to_bytes(),
        anc.request_transparency().to_bytes(),
        anc.request_set_enabled(True).to_bytes(),
        anc.request_enabled().to_bytes(),
    ]


def test_no_steps_is_not_success() -> None:
    """An empty plan has changed nothing, so it must not read as a completed change."""
    assert not control.apply(Session(FakeConnection([])), []).complete
