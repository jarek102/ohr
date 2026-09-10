# Commands

Only commands **confirmed against real hardware** are specified here — see
[evidence](provenance.md). Entries are added as devices demonstrate them.

All values are big-endian. Words are given as the request; the response word is the
same feature and operation with type 2 (see [framing](framing.md)).

## Feature 0 — core

### `0x0001` — feature list · `0x0002` — continuation

Empty payload. Reply:

| Bytes | Meaning |
|---|---|
| 0 | continuation flag — true **only when equal to 1** |
| 1.. | `(feature id, version)` pairs |

An empty payload is valid and means no continuation and no features. An unpaired
trailing byte is dropped, not treated as a version of zero. Unrecognised ids should be
retained with their version — firmware adds capabilities over time, and discarding
unknown ids understates what a device supports.

**Discovery is a two-command sequence.** Send `0x0001`; only if the flag is set, send
`0x0002` and merge. A client that issues `0x0002` alone, or ignores the flag, can
obtain a partial map — which matters, because feature 10's version selects which
connection-command family a device uses.

The flag being an equality test rather than a truthiness test is pinned by a vector; a
non-zero test would issue spurious continuation requests.

Observed feature maps for both devices are in
[`vectors/features.json`](../../vectors/features.json).

## Feature 3 — power

### `0x0603` — battery level

Empty payload. The reply has **two shapes**, and they treat `0xff` differently:

| Length | Shape | `0xff` |
|---|---|---|
| 1 | single level | **no special meaning** — decodes as 255/100 = 2.55 |
| ≥ 3 | left, right, case | **unavailable** |

Each byte is a level in hundredths: `0x46` = 70 = 0.70. Lengths 0 and 2 are invalid and
must be rejected, so a truncated triplet cannot be read as a single level. Bytes beyond
the third are not consumed — a field ignored here is not proven to be padding, so do
not assign it a meaning.

The `0xff` asymmetry between the two shapes is the likeliest source of a wrong reading
and is pinned by a vector.

*Unavailable* means the device declined to report that field. It does not mean empty,
and it does not reliably mean "in the case".

**There is no defined aggregate.** No rule for combining the three fields into a single
percentage has been established by observation, so any such number would be invented.
Present the fields.

### `0x060e` — battery types

Empty payload. Reply is **two independently decoded bytes**; fewer is invalid.

| Value | Label |
|---|---|
| 0 | micPower |
| 1 | vdl |
| 2 | varta |
| 3 | synergy |
| 4 | gp |
| 5 | mbt |
| 255 | invalid |

These identify **hardware battery type**. They are not charge levels, and they are not
a left/right/case descriptor. The physical meaning of the two positions is not
established.

Observed: `01 ff` on the over-ear model, `05 ff` on the earbuds.

## Feature 10 — device management

Not yet specified here. One fact is confirmed by observation and worth recording,
because it changes which commands apply:

**Feature 10 at version ≥ 4 uses address-based commands; below 4, index-based.** Both
devices observed so far report below 4 (versions 2 and 3), so both use the index
family. Read the feature map at connect time rather than assuming — a firmware update
can move a device across that boundary.

## Not yet specified

ANC, the equaliser and the connection-management command set are not
specified here yet — they are present in neither the vectors nor the code. They will
be added as each is exercised against a device and captured.
