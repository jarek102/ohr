"""The write path: every change is proved by a read.

**A write in this protocol acknowledges without reporting state.** The reply to a
setter is an empty acknowledgement — it says the frame was received, not that anything
changed. So an implementation that treats a successful send as a successful change is
wrong on this hardware, and would be wrong in a way that looks fine right up until a
device silently declines something.

Everything here therefore pairs a write with the read that proves it, and a change is
reported as applied only when the read agrees.

A second property shapes this module: **user-facing settings are not single commands.**
Selecting one noise-control mode takes up to two writes, so *partially applied* is a
reachable state and cannot be collapsed into a boolean. :func:`apply` stops at the
first step that fails and returns what has happened so far, leaving the caller holding
enough information to say what the device is now — and to put it back.

Pure: no I/O of its own. It drives a :class:`ohr.session.Session`, which drives
whatever transport the platform supplied.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from .errors import ProtocolError
from .frame import Frame, MessageType
from .session import Session


@dataclass(frozen=True, slots=True)
class Step:
    """One write, and the read that proves it landed.

    A step carries its own verification rather than leaving it to the caller, because
    the read that proves a write is not always the obvious counterpart: the setter and
    the getter for one setting sit on different operations, and in one case on a
    different feature entirely.
    """

    label: str
    write: Frame
    read: Frame
    decode: Callable[[bytes], Any]
    expect: Any


@dataclass(frozen=True, slots=True)
class Outcome:
    """What happened to one :class:`Step`.

    ``acknowledged`` and ``ok`` are deliberately separate. The device can acknowledge a
    write and then not have made the change — that combination is not a contradiction
    here, it is the case this module exists to detect.
    """

    step: Step
    acknowledged: bool
    observed: Any = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.acknowledged and self.error is None and self.observed == self.expect

    @property
    def expect(self) -> Any:
        return self.step.expect

    def describe(self) -> str:
        if self.ok:
            return f"{self.step.label}: {self.observed!r}"
        if self.error:
            return f"{self.step.label}: {self.error}"
        if not self.acknowledged:
            return f"{self.step.label}: not acknowledged"
        return (
            f"{self.step.label}: device still reports {self.observed!r}, "
            f"expected {self.expect!r}"
        )


@dataclass(frozen=True, slots=True)
class Applied:
    """The result of a sequence: every step attempted, in order.

    ``complete`` is the only thing a caller may treat as success. When it is false,
    ``outcomes`` says exactly how far the sequence got, which is what an undo needs.
    """

    outcomes: tuple[Outcome, ...] = field(default_factory=tuple)

    @property
    def complete(self) -> bool:
        return bool(self.outcomes) and all(o.ok for o in self.outcomes)

    @property
    def failed(self) -> Outcome | None:
        return next((o for o in self.outcomes if not o.ok), None)

    def describe(self) -> str:
        return "\n".join(o.describe() for o in self.outcomes)


def apply(
    session: Session,
    steps: Sequence[Step],
    *,
    timeout: float = 5.0,
    attempts: int = 3,
    interval: float = 0.15,
) -> Applied:
    """Run ``steps`` in order, verifying each by read-back. Stop at the first failure.

    Stopping matters. These sequences are ordered so that the intermediate states are
    the least surprising ones available, and continuing past a step that did not take
    would drive the device somewhere no one chose.

    ``attempts`` re-reads before giving up: the acknowledgement arrives before the
    change is necessarily observable, and one slow read is not evidence that a write
    was refused. Only the read is repeated — **the write is never re-sent**, because a
    setter that did take effect must not be applied twice.
    """
    if attempts < 1:
        raise ValueError("attempts must be at least 1")

    outcomes: list[Outcome] = []
    for step in steps:
        outcome = _run(session, step, timeout=timeout, attempts=attempts, interval=interval)
        outcomes.append(outcome)
        if not outcome.ok:
            break
    return Applied(tuple(outcomes))


def _run(
    session: Session, step: Step, *, timeout: float, attempts: int, interval: float
) -> Outcome:
    try:
        acknowledgement = session.request(step.write, timeout=timeout)
    except ProtocolError as exc:
        return Outcome(step, acknowledged=False, error=f"write failed: {exc}")

    if acknowledgement.type is MessageType.ERROR:
        # An error reply is an answer, and it means the setting is now unknown rather
        # than unchanged. Read anyway: the caller needs the state, not the verdict.
        state, why = _read(session, step, timeout=timeout)
        return Outcome(
            step,
            acknowledged=False,
            observed=state,
            error=why or "device rejected the write",
        )

    observed: Any = None
    error: str | None = None
    for attempt in range(attempts):
        if attempt:
            time.sleep(interval)
        observed, error = _read(session, step, timeout=timeout)
        if error is None and observed == step.expect:
            break
    return Outcome(step, acknowledged=True, observed=observed, error=error)


def _read(session: Session, step: Step, *, timeout: float) -> tuple[Any, str | None]:
    try:
        reply = session.request(step.read, timeout=timeout)
    except ProtocolError as exc:
        return None, f"read-back failed: {exc}"
    if reply.type is MessageType.ERROR:
        return None, "read-back returned an error frame"
    try:
        return step.decode(reply.payload), None
    except ProtocolError as exc:
        return None, f"read-back did not decode: {exc}"
