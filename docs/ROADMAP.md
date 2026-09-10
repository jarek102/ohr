# Roadmap

What is not built yet, in the order it makes sense to build it, with a testable exit
condition for each step.

Current state: the pure codec, the specification, and the vectors. **Nothing talks to a
device yet** — there is no transport implementation, and no write of any kind has ever
been sent to hardware.

## How this is sequenced

Four rules decide the order.

**Reads before writes.** Every read is non-mutating and can be exercised freely. The
first write is a genuine risk boundary and is crossed once, deliberately, with the
smallest reversible change available.

**Confirm before specifying.** A command enters `docs/protocol/` only after a device
has demonstrated it, with a vector to match. See [evidence](protocol/provenance.md).

**Smallest slice that proves the shape, then stop.** Each milestone below is meant to
be usable on its own and reviewed before the next begins.

**Record before, restore after.** Any step that mutates real device state captures it
first and puts it back, and says so in the milestone.

## M1 — Reach the hardware

**Goal:** the library reads a battery level from a real headset.

- Linux transport backend: device enumeration over BlueZ, RFCOMM connect
- **Service resolution by UUID**, not by hard-coded channel ([ADR 002](adr/002-layering-and-platform-seams.md))
- Advisory-lock lease backend ([ADR 003](adr/003-control-channel-ownership.md))
- A small CLI — `ohr status` — as the first consumer

**Done when:** battery and feature map are read from two different models through the
public API, and the existing vectors still pass untouched.

**Risks:** UUID-based resolution is unproven here — every capture so far used a
hard-coded channel because SDP tooling was unavailable. If resolution fails, that is a
finding, not a reason to hard-code; fall back explicitly and record why.

One device is known to time out on a first connection attempt and succeed on a retry.
Build the retry in from the start and do not treat a first failure as absence.

## M2 — Complete the read surface

**Goal:** every read for status, noise control, equaliser and connections is confirmed
on hardware and specified.

- Noise control: enabled state, transparency state, submodes, level
- Equaliser: configuration, per-band gain, bass boost, mode
- Connections: peer count, peer details, own index, maximum, active device
- Charger state
- A vector and a `commands.md` entry for each

**Done when:** `ohr status` prints complete state for both models, and every command it
issues appears in the specification with an `observed` vector.

**Depends on:** M1.

## M3 — Noise-control writes

**Goal:** switch between the three noise modes, verifiably.

This is the first write ever sent to these devices. Capture full state before, restore
after, and verify by read-back rather than by the acknowledgement — **setters reply
with an empty acknowledgement that carries no state.**

- Set enabled / transparency / submode / level
- The three user-facing modes, which are **multi-command sequences**, not single
  opcodes — a partially applied sequence is a reachable state
- A read-back-and-verify helper, used by every write path

**Done when:** all three modes can be selected on both models, each confirmed by
read-back, and the original mode restored.

**Depends on:** M2.

## M4 — Equaliser writes

**Goal:** set band gains and bass boost.

- Per-band gain, bass boost, EQ mode
- Preset application, which is **N writes, one per band** — there is no single preset
  command, so partial application is real; apply all, then read all back
- Clamp to the device's own reported range, not to the encoding's range

**Done when:** a band can be changed, read back, and restored; a full preset applies
atomically from the user's point of view or reports precisely what failed.

**Depends on:** M3 (shares the verify helper and the write-safety discipline).

## M5 — Standalone application: status

**Goal:** an Adwaita window showing rich status for a selected device.

- Device selection, and "nothing connected" as a first-class state
- Battery presented as **individual fields** — no invented aggregate
- Charger, noise-control state, connection summary
- Lease-scoped polling; contention rendered as a state, never as a crash

**Done when:** the app is worth leaving open to monitor a headset.

**Depends on:** M2 only — this can proceed in parallel with M3 and M4.

## M6 — Standalone application: control

**Goal:** noise control and equaliser, from the app.

- Noise-mode control, **driven by per-device capability** rather than a fixed layout —
  the two models differ in what they offer
- Equaliser: bands, presets, bass boost
- Pending state during multi-command sequences; no optimistic lie

**Done when:** the app fully replaces the vendor application for these two features.

**Depends on:** M3, M4, M5.

## M7 — Connection management

**Goal:** see which devices hold the headset, and change that from the desktop.

- Peer list with status, distinguishing *connected* from *streaming*
- Connect and disconnect by index
- **Guard the controller's own index** — disconnecting it destroys the control channel
  the undo would need
- Never delete a pairing as a side effect

**Done when:** a slot can be freed and reclaimed from the desktop, with the own-index
case proven safe.

**Depends on:** M2 for reads, M3 for write discipline.

## M8 — Live state

**Goal:** state stays correct when something else changes it.

- Event subscription and dispatch — note subscribing **mutates session state**, so it
  is not a read-only operation and belongs behind the lease
- Broker lease backend, so two consumers can be live at once and share one subscription

**Done when:** a change made from another controller is reflected in the app without a
manual refresh, and two consumers can run simultaneously without contending.

**Depends on:** M2. Required before more than one consumer is live.

## Downstream

**Shell integration** — a quick-settings surface for noise control and battery, in a
separate project consuming this library. Unblocked by M3; wants M8 to stay honest about
current state. Tracked there, not here.

**Windows** — the core is deliberately free of platform and toolkit imports, and the
transport and lease seams are documented, so a second implementation is a port rather
than a rewrite. Not planned; see [ADR 001](adr/001-spec-and-vectors-are-the-artifact.md).

## Not planned

Capabilities some devices advertise that this project does not intend to implement
soon: renaming, find-device, button mapping, fit test, personalised sound, broadcast
audio. They are real and reachable, but none is specified or verified here, so each
would be a research task before it is a feature. Listed so their absence is visible
rather than forgotten.

## Open decisions

**Where the standalone application lives.** Recommendation: **its own repository**,
depending on this one. The library is meant to serve several front-ends — this app, a
shell, potentially a Windows implementation — and bundling one of them here privileges
it and drags a GUI toolkit into a repository whose selling point is having no
dependencies.

**Whether the app or the shell surface comes first** once M3 lands. Both are unblocked
at the same moment. The app is the better proving ground; the shell surface is the
thing used more often. Not decided here.
