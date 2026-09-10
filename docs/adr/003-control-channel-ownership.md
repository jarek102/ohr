# ADR 003 — Control-channel ownership: lease now, broker later

**Status:** accepted · 2026-09-09

## Context

A device has one control channel. More than one local process may want it: a
standalone application, a shell widget, a diagnostic script. Two processes opening
their own sockets to the same headset contend.

There is also a party we can never mediate — **the vendor's phone application** is a
peer on the same channel. Contention is already observable: one device has returned
`ECONNREFUSED` while the phone application was active, and another times out on a
first connection attempt and succeeds on a retry, repeatably.

So graceful failure is required no matter what mediation we choose. That materially
lowers the value of a heavyweight solution.

## Decision

**A `Lease` abstraction from day one, with a pluggable backend. Advisory-lock backend
first; broker when a second live consumer actually exists.**

Leases are **explicit** at the call site:

```python
with lease.acquire(address, timeout=2.0):
    ...
```

not acquired implicitly inside every call. Contention becomes a state the UI renders,
rather than an exception appearing at scattered call sites.

The lock is **per device address**, not global — driving both headsets at once is
fine.

### Staging

**Advisory lock.** A per-device lock file: `flock` on POSIX, a named mutex on Windows.
Both release automatically when the holding process dies, so there is no stale-lock
cleanup to get wrong — a real advantage over anything hand-rolled with pidfiles.
Sufficient while one consumer is live at a time. It serialises but does not coordinate:
each consumer performs its own reads.

**Broker.** A single long-lived owner holding the channel, clients over IPC. Becomes
necessary when two consumers must be live simultaneously — because event subscription
requires a *held* channel and only one subscriber is meaningful. A broker also fans
one subscription out to everyone, so a change made on the phone reaches every consumer.

The advisory lock is **kept underneath the broker** rather than replaced: it costs
nothing and guarantees the channel is never opened twice even if a stray process
bypasses the broker.

## The half-dead client

`flock` releases on process **death**, not on a process that is merely wedged. A stuck
client holding the lease blocks everyone.

Primary defence: **never hold a lease across an unbounded wait.** Every transport
operation takes a timeout, so a client cannot hang while holding one. This is why
timeouts are mandatory in `ohr.transport` rather than optional.

Secondary: a heartbeat in the lock file, letting an acquirer break a lease that has
gone stale. Treated as a last resort — breaking a lock held by a live-but-stuck process
risks it waking mid-frame. The broker largely dissolves this problem: once it is the
only lease holder, "half-dead client" becomes "supervise one daemon", which systemd
already does well.

## Alternatives considered

**Shell owns the socket, app is a client.** Reuses existing shell IPC and needs no new
daemon. Rejected: it makes the standalone application depend on the shell running,
which defeats the word *standalone*, and inverts the dependency so the app relies on
the shell rather than both relying on this library.

**No mediation; rely on connect failure.** Racy, produces poor error messages, and does
not cover the phone anyway.

## Consequences

The simple backend ships first and the daemon is not built before there is anything to
coordinate. Because the abstraction exists from the start, adding the broker is a
backend swap, not a rewrite — consumer code does not change.

The cost is one indirection that looks unnecessary while there is exactly one consumer.
That is accepted deliberately: it is cheap now and expensive to retrofit.
