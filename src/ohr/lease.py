"""Control-channel ownership.

One device has one control channel, and more than one local process may want it — a
standalone app, a shell widget, a diagnostic script. A lease makes that exclusion
explicit so contention is a state the UI can render rather than an exception scattered
through call sites.

**This mediates local clients only.** The vendor's phone application is a peer on the
same channel and cannot be coordinated with, so every caller must handle failure
regardless of which backend is in use. That is precisely why the simple backend is
viable.

Backends, in the order they are expected to arrive:

* **Advisory lock** — a per-device lock file (``flock`` on POSIX, a named mutex on
  Windows; both release automatically when the holding process dies, so there is no
  stale-lock cleanup to get wrong). Sufficient while a single consumer is live at a
  time. No shared state: each consumer does its own reads.
* **Broker** — a single long-lived owner holding the channel, with clients talking to
  it over IPC. Required once two consumers must be live at once, because event
  subscription needs a *held* channel and only one subscriber is meaningful.

Consumers see the same API either way; swapping backends is not a rewrite. That is the
entire reason this abstraction exists before the broker does.

Timeouts are not optional. ``flock`` releases on process death but **not** on a process
that is merely wedged, so a lease must never be held across an unbounded wait. Bound
every operation, and treat a heartbeat-based lease break as a last resort — breaking a
lock held by a live-but-stuck process risks it waking mid-frame.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Lease(Protocol):
    """Exclusive local claim on one device's control channel.

    Intended to be used as a context manager, so the claim is visible at the call
    site::

        with lease.acquire(address, timeout=2.0):
            ...

    :meth:`acquire` raises :class:`ohr.errors.DeviceBusy` rather than blocking
    forever when another local process holds the claim.
    """

    def acquire(self, address: str, *, timeout: float) -> "Lease":
        ...

    def release(self) -> None:
        ...

    def __enter__(self) -> "Lease":
        ...

    def __exit__(self, *exc: object) -> None:
        ...
