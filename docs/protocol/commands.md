# Commands

Only commands **confirmed against real hardware** are specified here — see
[evidence](provenance.md). Entries are added as devices demonstrate them.

All values are big-endian. Words are given as the request; the response word is the
same feature and operation with type 2 (see [framing](framing.md)).

Reads are listed first, then writes. **Read [Writes](#writes) before sending one** —
this protocol acknowledges a setter without reporting state, so the reply to a write is
not evidence that anything changed.

| Word | Command | Request payload |
|---|---|---|
| `0x0001` / `0x0002` | Feature list, and its continuation | empty |
| `0x0602` | Charger state | empty |
| `0x0603` | Battery level | empty |
| `0x060e` | Battery types | empty |
| `0x0804` | Equaliser mode | empty |
| `0x1000` | Equaliser configuration | empty |
| `0x1002` | Band gain | band index |
| `0x1009` | Bass boost | empty |
| `0x1400` | Paired-device count | empty |
| `0x1401` | Peer details | peer index |
| `0x1407` | Own peer index | empty |
| `0x1409` | Maximum connections | empty |
| `0x1805` | Transparency enabled | empty |
| `0x1a01` | Noise-control submodes | empty |
| `0x1803` | Transparency level | empty |
| `0x1a03` | Active level | empty |
| `0x1a05` | ANC enabled | empty |

Writes:

| Word | Command | Request payload |
|---|---|---|
| `0x1804` | Set transparency | flag byte |
| `0x1a00` | Set submode | identifier, state |
| `0x1a02` | Set level | percentage byte |
| `0x1a04` | Set ANC | flag byte |

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

### `0x0602` — charger state

Empty payload. One byte is a single result; two supply a pair. Further bytes are not
consumed.

| Value | Meaning |
|---|---|
| 0 | disconnected |
| 1 | charging |
| 2 | complete |

**This command does not share the shape of `0x0603`.** The over-ear model returns a
single battery level but *two* charger values, so the number of charger values cannot
be predicted from the battery shape — read both.

There is **no case field**, even on a model whose battery reading includes the case. A
case percentage therefore says nothing about whether the case is charging.

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

## Features 12 and 13 — noise control

**Two features, not one.** ANC is feature 13; transparency — letting outside sound
through — is feature 12, with its own command. The user-facing choice between *ANC*,
*Transparency* and *Off* is a combination of the two, not a single setting.

They are **not mutually exclusive on the wire.** Both were observed reading as enabled
at the same time on the over-ear model. Do not infer one from the other, and do not
treat the pair as a three-valued enum.

### `0x1a05` — ANC enabled · `0x1805` — transparency enabled

Empty payload. Reply is one byte: 0 off, 1 on. Other values are invalid — this is a
two-valued flag, not a truthiness test.

### `0x1a01` — submodes

Empty payload. Reply is `(identifier, state)` pairs; an odd-length payload is invalid,
because a trailing identifier with no state would otherwise read as a submode set to
zero. Zero pairs is a valid answer.

| Identifier | Name |
|---|---|
| 1 | anti-wind |
| 2 | comfort |
| 3 | adaptive |

Both devices returned the same three identifiers. State ranges differ by submode and
are not assumed here — anti-wind is known to accept more than two values — so states
are kept as raw numbers.

### `0x1a03` — active level · `0x1803` — transparency level

Empty payload. Reply is one byte, in hundredths: `0x64` = 1.0.

**Two levels are stored, and the two reads are not interchangeable.** Cycling the
over-ear model through all three modes while reading both:

| Flags | `0x1a03` | `0x1803` |
|---|---|---|
| ANC on, transparency on | 100 | 100 |
| ANC on, transparency off | 0 | 100 |
| both off | 0 | 100 |
| ANC off, transparency on | 100 | 100 |

`0x1803` never moved. `0x1a03` followed whichever path was active — mirroring the
transparency level whenever transparency was on, and reporting the ANC level otherwise.
The earbuds show the same split from the other side: `0x1803` reads 75 while `0x1a03`
reads 0, with transparency off.

So `0x1803` is the one that means the same thing every time it is called. A reading from
`0x1a03` is meaningful only alongside the flags it was taken with — comparing two of
them across a flag change compares two different quantities, and restoring one that way
writes it into the wrong slot.

**Not a proxy for whether noise control is active** either: the earbuds reported 0.0
while ANC read as enabled, which is simply their ANC level.

`0x1801` also answers, with a single byte, on both models. What it means has not been
established, so it is not specified here.

## Features 4 and 8 — equaliser

Bands and bass boost are feature 8. The **mode** — which processing chain is active —
is feature 4. That split is easy to miss.

### `0x0804` — mode

Empty payload.

| Value | Meaning |
|---|---|
| 0 | off |
| 1 | user equaliser |
| 2 | podcast |
| 3 | personalised sound |
| 4 | parametric equaliser |
| 5 | hearing enhancement |

Both devices returned **two bytes** (`00 00`). Only the first is the mode; the second
is not consumed and its meaning is not established.

### `0x1000` — configuration

Empty payload. At least three bytes:

| Byte | Meaning |
|---|---|
| 0 | number of bands |
| 1 | minimum gain, signed, tenths of a decibel |
| 2 | maximum gain, signed, tenths of a decibel |
| 3.. | not consumed; meaning not established |

Both devices returned `05 c4 3c 00 00` — five bands, −6.0 dB to +6.0 dB, with two
trailing bytes that are retained rather than interpreted.

### `0x1002` — band gain

Payload is the band index. Reply is **one signed byte holding tenths of a decibel**:
`0x1e` is +3.0 dB, `0xc4` is −6.0 dB, `0xff` is −0.1 dB.

Two mistakes this encoding invites, both pinned by vectors: reading the byte as whole
decibels gives ten times the real value, and reading it unsigned turns −6.0 dB into
+19.6 dB — above the maximum the same device advertises.

Unlike the battery triplet, **`0xff` here is not a sentinel**; it is the smallest
negative step.

Clamp to the range from `0x1000`, not to the range the encoding could carry.

### `0x1009` — bass boost

Empty payload. Reply is one byte: 0 off, 1 on.

## Feature 10 — device management

**Two command families exist**, selected by this feature's own version: at version 4
and above peers are addressed by Bluetooth address; below it, by index. Only the index
family is specified here, because that is what both observed devices report (versions 2
and 3). Read the feature map at connect time rather than assuming — a firmware update
can move a device across that boundary.

### `0x1400` — paired-device count

Empty payload. Reply is **two bytes, big-endian**, even for small counts. Accepting a
single byte would work by accident for small values and then misread larger ones.

### `0x1409` — maximum connections · `0x1407` — own peer index

Empty payload. Reply is one byte.

Both devices reported a maximum of 2 against 3 paired peers — so peers routinely
outnumber the connections available, and something has to give up a slot for a new
device to take one.

**Own index differs per headset.** The same host was index 0 on one device and index 2
on the other, so it must be read per device. It is worth knowing before any write:
disconnecting your own index would destroy the channel the undo would need.

### `0x1401` — peer details

Payload is the peer index. Reply:

| Byte | Meaning |
|---|---|
| 0 | index |
| 1 | device type — see below |
| 2 | status |
| 3.. | name, UTF-8, terminated by a zero byte |

If **any** of the first three bytes is `0xff` the slot is empty. That is how enumeration
knows to stop: walk upward from index 0 until an invalid entry appears.

Status is a bit field:

- **low two bits** — 0 disconnected, 1 Classic, 2 BLE, 3 both
- **bit 7** — the peer is not paired over Classic. This is a pairing fact, **not** an
  activity flag, and it must not disturb the link state in the low bits.

A name that runs to the end of the payload without a terminator is taken whole.

**Device type is not a device category.** The same peer reported *different* values on
the two headsets — a phone was type 2 on one and type 1 on the other, while a desktop
was 0 on both. Whatever it encodes, it is not a stable property of the peer, so it is
kept as a raw number and given no meaning here.

Real captures of this command are not published, because peer names are the owner's own
machine names. The vectors carry the observed byte layout with placeholder names; see
[`vectors/connections.json`](../../vectors/connections.json).

## Writes

Four writes are specified, all in noise control. Each has been sent to hardware and
confirmed by reading the setting back.

### The acknowledgement carries no state

A setter replies with an empty acknowledgement. It says the frame was received. It does
not say the setting changed, and there is no field in it that could. **Every write must
be verified by a read.**

An error reply is also an answer, and it means the setting is now *unknown* rather than
unchanged — so read it back after one of those too.

### A read-back is necessary, and not sufficient

The earbuds accepted `0x1804 01`, returned success, and answered the transparency read
with 1. Within a second the same read returned 0, and it stayed there. Repeated with
one earbud out of the case — the charger read confirming it, one bud charging and one
not — with the same result, so the case alone does not explain it. It reverts from
either starting mode, and within roughly a tenth of a second.

A device can therefore acknowledge a write, confirm it, and then abandon it. An
immediate read-back proves the device took the command; only continued observation
proves it kept it. Anything showing live state has to keep reading.

### `0x1a04` — set ANC · `0x1804` — set transparency

One flag byte: 0 off, 1 on. Both confirmed on both models.

Each setter sits one operation below its getter, on its own feature — ANC is 13,
transparency is 12. Sending the right operation to the wrong feature is accepted and
sets the other thing.

**Engaging ANC clears the transparency flag.** Writing `0x1a04 01` to a device that
already had ANC on still dropped transparency, so the side effect belongs to the write
rather than to a change of value.

The coupling runs **one way only**, which is easy to assume symmetric and is not:

| Write | Effect on the other flag |
|---|---|
| ANC on | transparency cleared |
| ANC off | transparency untouched |
| transparency on | ANC untouched — both then read as on |
| transparency off | ANC untouched |

Two consequences for anything that writes more than one flag. **Set ANC before
transparency**, or the second write undoes the first. And a transparency flag that
already reads as wanted must still be rewritten when an ANC-on write precedes it —
skipping it yields a sequence that verifies every write it makes and leaves the device
somewhere else.

### The three modes are sequences, not commands

There is no mode field. The user-facing choice is a position of two independent flags,
so selecting one takes up to two writes and can be **partially applied**:

| Mode | Writes |
|---|---|
| ANC | transparency off — only if it is on — then ANC on |
| Transparency | transparency on |
| Off | ANC off, then transparency off |

Two consequences worth stating plainly:

**Order is part of the specification.** Each sequence clears before it sets, so a
sequence that stops halfway leaves less processing running rather than two paths at
once.

**Selecting Transparency does not clear ANC.** Afterwards both flags read as on, which
is the state the over-ear model was found in. That is the device's behaviour, not an
omission.

Availability is a per-product decision that no read exposes — a device need not offer
*off*. Attempt the mode and verify; do not infer support from the feature map.

### `0x1a02` — set level

One byte, in hundredths, matching the read encoding: 0.5 is 50. Confirmed on the
over-ear model at 0, 40, 50 and 100.

**This write also clears the transparency flag**, the same way `0x1a04 01` does, and
for what looks like the same reason: it engages ANC. Writing the level the device
already reported still moved it out of transparency, so the side effect follows the
write itself, not a change of value.

Taken with the two stored levels described under `0x1a03`, this is *set the ANC level* —
which necessarily means selecting ANC. It does not touch the transparency level, which
has its own read at `0x1803` and no setter specified here.

A client changing the level must therefore re-read the flags, not just the level. An
undo that replays only the field it set will leave the device somewhere it never was.

### `0x1a00` — set submode

Identifier then state, the same pairing `0x1a01` returns. Not yet sent to hardware.

There is no read for a single submode: verify by re-reading all of them, which also
shows whether the device moved another submode in response. Accepted state ranges
differ per submode and are not advertised by any read.

## Not yet specified

Writes outside noise control — the equaliser and connection management. They will be
added the same way these were: exercised against hardware, confirmed by read-back, and
pinned by a vector.
