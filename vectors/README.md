# Test vectors

Language-neutral fixtures for the protocol. **These are the artifact.** Any
implementation — the Python core here, a C# one, anything else — is correct exactly
insofar as it reproduces these.

They exist from the first commit on purpose. Retrofitting fixtures out of tests
already written against internal APIs is far more painful than starting with them,
and a second implementation with no shared fixtures will drift silently.

## Files

| File | Covers |
|---|---|
| [framing.json](framing.json) | Frame encode/decode and stream reassembly |
| [battery.json](battery.json) | Battery level, types and charger |
| [features.json](features.json) | Feature-list payload decode |
| [anc.json](anc.json) | Noise control: reads, writes, and the mode sequences |
| [equaliser.json](equaliser.json) | Mode, configuration, band gain, bass boost |
| [connections.json](connections.json) | Peer count, peer details, own index, maximum |

Each file is `{"version": 1, "vectors": [...]}` and validates against
[schema.json](schema.json).

## Vector kinds

**`frame`** — a complete frame on the wire, with its decoded fields. Must round-trip:
decoding `bytes` yields the fields, and encoding the fields reproduces `bytes` exactly.

**`stream`** — a list of `chunks` delivered in order, the `frames` that should emerge,
and the `remainder` left buffered. Covers partial frames, several frames in one read,
and leading garbage. A read is not a frame; these prove an implementation knows that.

**`payload`** — a payload body and its decoded meaning, for one named command. No
framing involved.

**`sequence`** — the writes a named plan produces from a given starting state, in
order, each paired with the read that proves it.

That last kind exists because a user-facing setting is not always one command. A setter
here acknowledges without reporting state, so *which* read verifies *which* write is
part of the protocol rather than a detail of any one implementation — and so is the
order, since a sequence that stops halfway leaves the device somewhere real. A vector
that pinned only the bytes would let a second implementation send them in an order that
fails differently.

## Provenance — read this before adding a vector

Every vector carries a `provenance` block, and there are exactly two kinds:

- **`observed`** — captured from a real device. Carries `device` and `date`. These are
  facts about hardware behaviour, independently reproducible by anyone with the same
  model.
- **`constructed`** — hand-built to exercise a branch (a truncated frame, an invalid
  length). Carries a `rationale`. It asserts what *this specification* requires, not
  what a device was seen to do.

Every expected value must come from one of those two. If a value cannot be observed on
the wire, or justified from the specification, it does not belong here — see
[../docs/protocol/provenance.md](../docs/protocol/provenance.md).

When a `constructed` vector is later confirmed against hardware, promote it to
`observed` and record the date — don't add a second one.

## Devices

`device` is a model identifier, not a serial:

| Value | Model |
|---|---|
| `accentum-wireless` | Sennheiser ACCENTUM Wireless (over-ear) |
| `momentum-tw4` | Sennheiser MOMENTUM True Wireless 4 (earbuds) |

The two answer differently — most visibly, battery level is a single byte on the
over-ear model and three bytes on the earbuds. Vectors from both are kept for exactly
that reason.
