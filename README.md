# ohr

Vendor control protocol for Sennheiser Bluetooth headsets, over RFCOMM (Bluetooth).
An unofficial independent open replacement for Android app.

Supports:
 - battery
 - ANC
 - EQ
 - connection managemant

> **Status: pre-alpha.** All reads are implemented and verified against both devices.
> Noise control also writes — ANC, transparency and level — each confirmed by reading
> the setting back. The equaliser and connection management are still read-only. See
> [the roadmap](docs/ROADMAP.md).

## What is here

A **protocol specification** with **language-neutral test vectors**, and a Python
implementation of the pure parts. Written mostly with Claude.

```
docs/protocol/   the specification
vectors/         conformance fixtures — the contract
src/ohr/         Python: pure codec, plus the transport and lease interfaces
```

## Design in one paragraph

The core is pure: framing, payload codecs and the write path, with no I/O, no platform
imports, no GUI toolkit and no dependencies. Everything platform-specific sits behind two interfaces —
[`transport`](src/ohr/transport.py) for the Bluetooth socket and device enumeration,
[`lease`](src/ohr/lease.py) for control-channel ownership. That boundary is
[enforced by a test](tests/test_core_is_portable.py), not just documented, because it
is easy to break with one convenience import.

## Try it

```bash
python3 -m pytest
```

No install, no Bluetooth stack, no hardware — the codec is exercised entirely from the
vectors.

## Supported/tested devices

| Model | Battery shape |
|---|---|
| ACCENTUM Wireless (over-ear) | single level |
| MOMENTUM True Wireless 4 (earbuds) | left, right, case |

Other models in the range very likely speak the same protocol, but nothing here has
been verified against them. Vectors from more hardware are welcome.

## Documentation

| | |
|---|---|
| [docs/protocol/](docs/protocol/README.md) | The specification |
| [vectors/](vectors/README.md) | Fixtures, and the provenance rule for adding one |
| [docs/adr/](docs/adr/README.md) | Why the code is shaped this way |
| [docs/ROADMAP.md](docs/ROADMAP.md) | What is not built yet, and in what order |

## Licence

MIT — see [LICENSE](LICENSE).
