# Architecture decisions

Why the code is shaped this way. Each entry records a decision, what was rejected, and
what it costs — so a later reader can tell a deliberate choice from an accident.

| ADR | Decision |
|---|---|
| [001](001-spec-and-vectors-are-the-artifact.md) | The specification and vectors are the artifact; implementations are consumers |
| [002](002-layering-and-platform-seams.md) | Pure core, three platform seams, no GLib in the library |
| [003](003-control-channel-ownership.md) | Explicit leases; advisory lock now, broker when a second live consumer exists |

Supersede rather than edit: if a decision changes, add a new ADR and mark the old one
superseded. The reasoning behind a reversed decision is usually worth more than the
decision was.
