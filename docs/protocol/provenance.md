# Evidence

How to tell how solid any claim in this specification is, and what standard a new one
has to meet.

## The standard

**Every command specified here has been confirmed by talking to a device.** Send a
request to a headset, record the reply, decode it — and anyone with the same model can
reproduce the result independently.

That is the whole basis of this document. It is why [commands.md](commands.md) is
shorter than the protocol: a behaviour is described once a device has demonstrated it,
and not before.

So **absence means "not yet confirmed"**, never "does not exist".

## Vectors

[`vectors/`](../../vectors/README.md) applies the same standard mechanically. Every
fixture declares one of two kinds, and a test fails the build if the declaration is
missing or malformed:

| Kind | Means | Requires |
|---|---|---|
| `observed` | A real device was seen to do this | `device`, `date` |
| `constructed` | This specification requires it | `rationale` |

A `constructed` vector asserts a **rule** — that a two-byte battery payload must be
rejected, say — and its rationale explains why the rule matters. It does not claim
hardware was seen to behave that way. The distinction is load-bearing: it lets a reader
tell a measurement from a design decision at a glance.

When a `constructed` vector is later confirmed against hardware, **promote it** —
change the kind, add device and date. Do not add a second vector for the same case.

**Never edit an `observed` vector to make code pass.** It records what hardware sent.
If code disagrees with it, the code is wrong.

## Devices and dates

Observed entries name a model, never a serial or address:

| Identifier | Model |
|---|---|
| `accentum-wireless` | Sennheiser ACCENTUM Wireless (over-ear) |
| `momentum-tw4` | Sennheiser MOMENTUM True Wireless 4 (earbuds) |

Dates are absolute, and they matter more than they might appear to. **Firmware changes
behaviour**: the connection-command family a device uses is selected by a feature
version, which a firmware update can move. An undated observation is therefore much
weaker than a dated one, because it cannot be placed relative to a device's firmware.

The two models also differ from each other in observable ways: battery arrives as one
value from the over-ear model and three from the earbuds. Fixtures are kept from both
so that a decoder cannot pass by handling only one.

## Labels are not wire data

Some names in this project are readability aids rather than protocol.

Feature **ids and versions** are reported by the device. The **names** attached to them
are ours — chosen to describe behaviour, confirmed for some features and not for
others. Wherever such a label appears it is documented as a label, and **where a name
and an id disagree, the id is authoritative.**

Battery type labels (`vdl`, `mbt`, …) are the same: the numeric values are observed,
the words are labels, and the physical meaning of the two positions is not established.

## Adding to this specification

1. Exercise the command against a device you own and capture the exact bytes.
2. Add an `observed` vector with the model and the date.
3. Describe the behaviour in [commands.md](commands.md).
4. Add `constructed` vectors for the edge cases the specification requires — invalid
   lengths, sentinel values, boundaries — each with a rationale.

Captures from models not listed above are especially welcome; the protocol is believed
to be shared across the range, but that is currently an assumption rather than a
finding.
