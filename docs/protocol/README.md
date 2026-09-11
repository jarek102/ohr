# Protocol specification

A vendor control protocol carried over Bluetooth RFCOMM, used by several Sennheiser
headsets. Independently documented from observed device behaviour.

| Page | Covers |
|---|---|
| [framing.md](framing.md) | Frame layout, the command word, stream reassembly, reply correlation |
| [commands.md](commands.md) | Commands confirmed against hardware |
| [provenance.md](provenance.md) | What may be recorded here, and how to tell how solid a claim is |
| [prior-art.md](prior-art.md) | Other implementations: what they corroborate, and where one disputes this |

Start with [framing.md](framing.md) — the framing is shared by every command, and two
of its properties (the length field excludes four header bytes; a read is not a frame)
account for most implementation mistakes.

The normative form of everything here is
[`vectors/`](../../vectors/README.md). Where prose and a vector disagree, the vector
wins: it is executable and the prose is not.

## Scope

[commands.md](commands.md) is smaller than the protocol. Only commands confirmed by
talking to a device are specified — absence means *not yet confirmed*, not *does not
exist*. See [evidence](provenance.md) for the standard a new entry has to meet.

Two models have been observed:

| Model | Notes |
|---|---|
| ACCENTUM Wireless | over-ear; single-value battery |
| MOMENTUM True Wireless 4 | earbuds; left/right/case battery |

Others in the range very likely speak the same protocol. Nothing here is verified
against them, and firmware version demonstrably changes behaviour, so treat any
extrapolation as a hypothesis until a device confirms it.
