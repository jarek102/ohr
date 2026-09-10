# ADR 002 — Pure core, three platform seams, and no GLib anywhere near it

**Status:** accepted · 2026-09-09

## Context

Two consumers are expected: a standalone Adwaita application and a shell
(py-desktop-3) that reuses the same logic. The shell is GLib/Astal-based, so driving
I/O from the GLib main loop is the path of least resistance — and would be a mistake.

GLib does exist on Windows, but pulling it into shared code means any future non-GTK
consumer carries the whole stack to talk to a Bluetooth socket. It also makes the
codec untestable without a main loop, for no benefit: framing and payload decoding are
pure functions.

## Decision

**The core is pure.** Framing, word packing, payload codecs. No I/O, no platform
imports, no toolkit, no third-party dependencies.

**Platform-specific work sits behind two interfaces** — `ohr.transport` (socket and
device enumeration) and `ohr.lease` (ownership, see
[ADR 003](003-control-channel-ownership.md)). Neither has an implementation in core.

There are **three seams**, not one:

| Concern | Linux | Windows |
|---|---|---|
| RFCOMM socket | `AF_BLUETOOTH` / `BTPROTO_RFCOMM` | WinRT `Rfcomm` + `StreamSocket` |
| Device enumeration | BlueZ over D-Bus | WinRT `BluetoothDevice` |
| Cross-process lease | `flock` | named mutex |

**GLib is excluded from the library entirely.** The core is synchronous; consumers
adapt at their own edge. The shell integrates with GLib on its side; the library does
not know GLib exists.

**Services are resolved by UUID, never by channel number.** Channel numbers were
originally hardcoded from observation because SDP tooling was unavailable, and a
firmware update can invalidate them. The Windows API is UUID-based regardless, so this
is both more portable and more robust on Linux than the thing it replaces.

## Enforcement

Documented rules of this kind rot. `tests/test_core_is_portable.py` parses every core
module and fails on an import of `socket`, `fcntl`, `msvcrt`, `ctypes`, `subprocess`,
`dbus`, `gi`, `winrt` or `bleak`, and asserts core dependencies stay empty.

`bleak` is on that list deliberately. It is the best-known cross-platform Python
Bluetooth library and it is **BLE-only**, while this protocol runs over RFCOMM
(Classic). It is the most likely wrong turn available, so the gate names it.

## Consequences

The codec is exercised entirely from `vectors/` with no Bluetooth stack, on any OS.
Porting to another language is a straightforward read of pure functions. And per
[ADR 001](001-spec-and-vectors-are-the-artifact.md), if Windows goes to C# the Python
seams reduce to Linux only — simpler, not more complex.

The cost is indirection: reaching a device means a transport implementation rather
than opening a socket inline. That is a real cost and it is accepted.
