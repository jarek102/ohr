# ADR 001 — The specification and vectors are the artifact, not the Python package

**Status:** accepted · 2026-09-09

## Context

This work started as a library to be consumed by one Linux shell. Two things changed
that framing.

A Windows application is plausible, and the preferred UI there is WinUI 3 — which is
C#. Consuming a Python library from C# means embedding CPython or running a local
service: a runtime dependency and a debugging seam inside what should be a single
executable. Meanwhile Bluetooth on Windows is reached through WinRT, which is
first-class from C# and awkward from Python.

Separately, the expensive part of this project was never the code. It was determining
what the bytes mean. The pure codec is a few hundred lines; the knowledge it encodes
took far longer to obtain.

## Decision

**The protocol specification and the test vectors are the primary artifact.**
Implementations — the Python one here, a C# one later, any other — are consumers of
that artifact and are correct exactly insofar as they reproduce the vectors.

Consequences that follow directly:

- `vectors/` exists from the first commit, not once a second implementation appears.
  Retrofitting fixtures out of tests already written against internal APIs is far more
  work, and two implementations without shared fixtures drift silently.
- Vectors are language-neutral JSON. No Python types, no pickles, nothing that
  presumes the consumer.
- A second implementation is a normal outcome, not a failure of reuse.

## Alternatives considered

**One Python library plus PySide6 on Windows.** A single codebase, and genuinely the
strong second choice. Rejected because it means fighting Python-to-WinRT bindings for
the Bluetooth layer and accepting a non-native UI, to avoid duplicating a small pure
function set that vectors can keep in sync anyway.

**Bridge via pythonnet or IronPython.** IronPython trails CPython badly and has no
C-extension support; pythonnet works but puts an embedded interpreter inside a desktop
app. Both solve a problem we do not have to have.

## Consequences

Good: the durable output is useful to anyone, in any language. A specification built
from observed device behaviour is independently reproducible by anyone with the same
hardware, which is a firmer foundation than an implementation alone. And the codec
becomes trivially testable with no Bluetooth stack present.

Bad: protocol logic will exist more than once, and can drift. The vectors are the
entire mitigation, so a change to decoding behaviour that does not come with a vector
is a defect regardless of whether tests pass.
