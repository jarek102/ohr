# Contributing conventions

For anyone — human or agent — changing this repository.

**Read first:** [README](README.md) for what this is, then
[docs/protocol/](docs/protocol/README.md) for the specification and
[docs/ROADMAP.md](docs/ROADMAP.md) for what is planned and in what order.

```
docs/protocol/   the specification — framing, commands, evidence standard
docs/adr/        why the code is shaped this way
vectors/         conformance fixtures, and their schema
src/ohr/         the pure codec, plus the transport and lease interfaces
tests/           the vector runner and the layering gate
```

Run everything with `python3 -m pytest`. No install, no Bluetooth stack and no hardware
are required — the codec is exercised entirely from the fixtures.

## The rules that matter

**1. The vectors are the contract.** They are the artifact this project exists to
produce ([ADR 001](docs/adr/001-spec-and-vectors-are-the-artifact.md)); implementations
are consumers. A change to decoding behaviour that does not come with a vector is a
defect even if every test passes.

**2. Never edit an `observed` vector to make code pass.** It records what real hardware
sent. If code disagrees with it, the code is wrong. A `constructed` vector may be
corrected — say why in its `rationale`.

**3. The core stays pure.** No I/O, no platform imports, no GUI toolkit, no
dependencies. Platform work goes behind `transport` and `lease`
([ADR 002](docs/adr/002-layering-and-platform-seams.md)). This is enforced by
`tests/test_core_is_portable.py`, which fails on an import of `socket`, `fcntl`, `gi`,
`winrt`, `bleak` and friends — if that test blocks you, move the code rather than
extending the allowlist.

**4. Confirm before specifying.** A command enters `docs/protocol/` only once a device
has demonstrated it, with a vector to match. Absence from the specification means *not
yet confirmed*, never *does not exist*. See [evidence](docs/protocol/provenance.md).

**5. Writes acknowledge without reporting state.** Every setter replies with an empty
acknowledgement, so a successful write is never evidence that anything changed. Verify
by read-back. Several user-facing operations are multi-command sequences, which makes a
partially applied state reachable.

**6. Record before, restore after.** Anything exercised against a real device captures
its state first and puts it back. If a setting was chosen deliberately by whoever owns
the hardware, verify it read-only instead.

**7. Resolve services by UUID, not by channel number.** Channel numbers are
observations that firmware can invalidate.

**8. Smallest slice that proves the shape, then stop.** Prefer a reviewable step over a
complete one.

## Adding to the specification

1. Exercise the command against a device and capture the exact bytes.
2. Add an `observed` vector with the model and the date.
3. Describe the behaviour in [commands.md](docs/protocol/commands.md).
4. Add `constructed` vectors for the edge cases the specification requires — invalid
   lengths, sentinels, boundaries — each with a rationale.

## Decisions

Architecture decisions live in [docs/adr/](docs/adr/README.md) and are superseded
rather than edited. If a decision turns out wrong, add a new record and mark the old one
superseded; the reasoning behind a reversal is usually worth more than the original.
