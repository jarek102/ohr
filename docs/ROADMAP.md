# Roadmap

Where this is going, in the order it makes sense to get there.

**Today:** the library reads everything and writes noise control. Every read for status,
noise control, the equaliser and connections is implemented, confirmed against both
models, and specified. Noise-control writes — ANC, transparency, level — are confirmed
by read-back on hardware. The equaliser and connection management are still read-only.

## At a glance

| | Goal | Status |
|---|---|---|
| **M0** | Specification, vectors, pure Python codec | **shipped** · 2026-09-09 |
| **M1** | Reach the hardware — read a battery level from a real headset | **shipped** · 2026-09-09 |
| **M2** | Complete the read surface — status, ANC, equaliser, connections | **shipped** · 2026-09-09 |
| **M3** | ANC writes — switch between ANC, Transparency and Off | **shipped** · 2026-09-10 |
| **M4** | Equaliser writes — band gains, bass boost, presets | not started · next |
| **M5** | Adwaita application: status | **shipped** · 2026-09-13 |
| **M6** | Adwaita application: control | not started · after M3, M4, M5 |
| **M7** | Connection management — see and change who holds the headset | not started · after M3 |
| **M8** | Live state — stay correct when something else changes it | not started · after M2, and now load-bearing |
| **W1** | A C# codec passing the same vectors | not started · after M2 |
| **W2** | WinRT transport and a WinUI 3 application | not started · after W1, M3 |

M5 needs only M2, so a usable read-only application can be built alongside the write
work rather than queued behind it. W1 needs no Bluetooth at all.

## Milestones

### M1 — Reach the hardware

**Goal:** the library reads a battery level from a real headset.

- Linux transport backend: device enumeration over BlueZ, RFCOMM connect
- Service resolution by UUID rather than a hard-coded channel
  ([ADR 002](adr/002-layering-and-platform-seams.md))
- Advisory-lock lease backend ([ADR 003](adr/003-control-channel-ownership.md))
- A small CLI, `ohr status`, as the first consumer

**Done when:** battery and feature map are read from two different models through the
public API, with the existing vectors untouched.

**Outcome:** shipped, with one finding. **Service discovery does not answer on either
device.** Searches for the vendor service, the Serial Port profile and even the public
browse group all returned success with zero records, while BlueZ showed the same
devices advertising those UUIDs. So the channel is resolved in three steps — supplied,
then remembered, then discovered — and when none answers, the connection fails rather
than guessing. No channel numbers ship in the library.

### M2 — Complete the read surface

**Goal:** every read for status, ANC, equaliser and connections is confirmed on
hardware and specified.

- ANC: enabled state, transparency state, submodes, level
- Equaliser: configuration, per-band gain, bass boost, mode
- Connections: peer count, peer details, own index, maximum, active device
- Charger state
- A vector and a `commands.md` entry for each

**Outcome:** shipped. `ohr probe` exercises sixteen reads; all decoders were correct
against both models on the first attempt. Three findings went into the specification:
ANC and transparency are independent flags and were seen enabled together; the charger
command returns two values on the model whose battery returns one; and peer *device
type* is not a device category, since the same peer reports different values on the two
headsets.

### M3 — ANC writes

**Goal:** switch between the three modes — ANC, Transparency, Off — verifiably.

The first write ever sent to these devices.

- Set enabled, transparency, submode, level
- The three user-facing modes, each a multi-command sequence rather than a single
  opcode, so a partially applied sequence is a reachable state
- A read-back-and-verify helper, shared by every write path

**Done when:** all three modes can be selected on both models, each confirmed by
read-back, and the original state restored.

**Outcome:** shipped. All three modes selected and confirmed on both models, each
restored afterwards — and four findings, the first of which took three attempts to run
down.

**Transparency on the earbuds needs both out of the charging case.** The write was
acknowledged, the read-back returned *on*, and a moment later the same read returned
*off* and stayed there. With one earbud out it reverted identically; with both out it
holds indefinitely, from either starting mode. The charger read tells the three cases
apart — `01 01`, `01 00`, `00 00` — so it is a checkable precondition rather than a
mystery.

The general rule outlives its explanation, and outranks the milestone: **a confirmed
read-back is not proof a setting persists.** A device can acknowledge a write, confirm
it, and then abandon it. Immediate verification proves the command was taken, not kept.

Passthrough was once reported reaching one earbud only, and did not reproduce in any
later attempt. The likeliest explanation is an earbud that left the case without
joining the pair — and **nothing specified here would catch that**, since a battery
level is reported for an earbud whether or not it is participating. Feature 14 (`tws`)
is the obvious place to look and is not specified.

Second, and the one that cost the most: **the flags are coupled, one way.** Engaging
ANC clears transparency — including when ANC is already on, so the side effect belongs
to the write. Turning ANC off does not touch it, and neither direction of transparency
touches ANC. Writing the level does clear it, being ANC engagement by another name.

Third: **there are two levels, and two reads.** `0x1803` reports the transparency level
and never moved across a full cycle of the three modes. `0x1a03` reports the ANC level
while transparency is off, and full scale while it is on — not the transparency level,
which read 0.75 on the earbuds at the moment `0x1a03` said 1.00. A reading from the
latter means nothing without the flags it was taken with.

Fourth follows from the second, and was found the hard way: **skipping a write for a
flag that already reads correctly is not safe.** An ANC-on write ahead of it clears the
flag, so the sequence verifies everything it sends and still ends somewhere else. That
is exactly what the first restore did.

Together these killed the obvious undo. Putting a device back means reconciling a whole
snapshot, in an order that respects the coupling, re-reading between rounds — not
replaying the field that was changed.

### M4 — Equaliser writes

**Goal:** set band gains and bass boost.

- Per-band gain, bass boost, EQ mode
- Preset application, which is one write per band — there is no single preset command,
  so partial application is real
- Clamping to the device's own reported range rather than the encoding's

**Done when:** a band can be changed, read back and restored; a preset either applies
completely or reports precisely what failed.

### M5 — Adwaita application: status

**Goal:** a window showing rich status for a selected device.

- Device selection, with "nothing connected" as a first-class state
- Battery as individual fields, with no invented aggregate
- Charger, ANC state, connection summary
- Lease-scoped polling, with contention shown as a state rather than an error

**Done when:** the application is worth leaving open to monitor a headset.

**Outcome:** shipped as [ohr-gtk](https://github.com/jarek102/ohr-gtk).

Three design decisions came out of the protocol work rather than from the toolkit.
**Reading is tiered** — identity once, moving parts every three seconds, settings and
peers every half-minute — because a window left open would otherwise hold the channel
busy forever and nothing here can show that is harmless. **A mode change re-reads the
flags in the operation that writes them**, since a plan built from the last poll
verifies perfectly and selects the wrong mode. And **all Bluetooth work sits on a thread
that owns the lease, the socket and the session together**, so a five-second timeout
does not freeze the window during exactly the cases worth watching.

Connections is the section that earns leaving it open: who is paired, who holds one of
the two slots, and which entry is this computer. That is the thing the vendor
application is worst at.

One limit worth stating: the layout is built from the feature map, but **both models
here have every feature the window draws**, so nothing actually disappears on either.
That logic is for models that differ and is so far unexercised.

### M6 — Adwaita application: control

**Goal:** ANC and equaliser, from the application.

- Mode control driven by per-device capability rather than a fixed layout, because the
  two models differ in what they offer
- Equaliser: bands, presets, bass boost
- A pending state during multi-command sequences

**Done when:** the application replaces the vendor one for these two features.

### M7 — Connection management

**Goal:** see which devices hold the headset, and change that from the desktop.

- Peer list with status, distinguishing *connected* from *streaming*
- Connect and disconnect by index
- A guard on the controller's own index, since disconnecting it destroys the channel
  the undo would need

**Done when:** a slot can be freed and reclaimed from the desktop, with the own-index
case proven safe.

### M8 — Live state

**Goal:** state stays correct when something else changes it.

- Event subscription and dispatch — subscribing mutates session state, so it belongs
  behind the lease
- Broker lease backend, so two consumers can be live at once sharing one subscription

**Done when:** a change made from another controller appears without a manual refresh,
and two consumers run simultaneously without contending.

M3 raised this milestone's importance. A device was seen to accept a setting, confirm
it, and drop it a second later on its own — no other controller involved. Any surface
that stops reading after a write can show a state the device is not in.

## Windows

A parallel track rather than a continuation: different language, different stack, and
the first half needs no Bluetooth.

Windows means C# and WinUI 3, not Python. WinRT is first-class from C# and awkward from
Python, and a WinUI application should be a single executable rather than one embedding
an interpreter.

### W1 — A C# codec passing the same vectors

**Goal:** a second implementation of the pure codec, checked against `vectors/`
unchanged.

- Framing, word packing, stream reassembly
- Every payload codec the specification covers at that point
- The same JSON fixtures, with no Python in the loop

**Done when:** both implementations pass identical vectors, and deliberately breaking
one is caught.

**Why it comes first:** this is the first real test of the premise that shared fixtures
can keep two implementations honest. If that fails, it is far cheaper to find out here —
with no hardware, transport or UI in the picture — than after an application has been
built on the assumption.

### W2 — WinRT transport and a WinUI 3 application

**Goal:** read status and control ANC on Windows.

- WinRT `Rfcomm` and `StreamSocket` transport, resolved by service UUID
- Named-mutex lease, matching the POSIX advisory lock's semantics including release on
  process death
- WinUI 3 application: status, ANC, equaliser

**Known risk:** BLE libraries do not apply — this protocol is RFCOMM (Classic). It is
the most likely wrong turn on this track.

## Downstream

**Shell integration** — a quick-settings surface for ANC and battery, in a separate
project consuming this library. Unblocked by M3, and wants M8 to stay honest about
current state. Tracked there, not here.

---

## How this is sequenced

Four rules decide the order above.

**Reads before writes.** Every read is non-mutating and can be exercised freely. The
first write is a real risk boundary, crossed once and deliberately, with the smallest
reversible change available.

**Confirm before specifying.** A command enters `docs/protocol/` only once a device has
demonstrated it, with a vector to match — see [evidence](protocol/provenance.md).

**Smallest slice that proves the shape, then stop.** Each milestone is meant to be
usable on its own and reviewed before the next begins.

**Record before, restore after.** Any step that mutates real device state captures it
first and puts it back.

One property of the protocol shapes several milestones: **writes reply with an
acknowledgement carrying no state**, so a successful write is never evidence that
anything changed. Every write path verifies by read-back, which is why M3 builds that
helper before M4 and M7 reuse it.

## Open decisions

**Where each piece lives.** The line falls between implementations of the protocol and
applications built on them:

- **This repository** holds the specification, the vectors, and every implementation of
  the protocol — Python now, C# at W1. Implementations sit beside the vectors because
  the fixture set is the one thing that must never fork.
- **Applications live in their own repositories**, each depending on the library for its
  platform. Bundling one front-end here would privilege it, and drag a GUI toolkit into
  a repository whose selling point is having no dependencies.

So: Adwaita and WinUI applications outside; Python and C# codecs inside. The Adwaita
one now exists as [ohr-gtk](https://github.com/jarek102/ohr-gtk), which settles the
first half of this in practice rather than on paper.

**Whether the application or the shell surface comes first** once M3 lands. Both are
unblocked at the same moment. The application is the better proving ground; the shell
surface is used far more often.

## Leads

Things known to exist because a device does them, with no command identified yet.
Listed because a lead with a known right answer is much cheaper to chase than one
without.

Four of these are now **found and specified** — the codec, the firmware version, the
prompts setting and the on-head detection setting. What remains:

**The live wear state.** The setting is readable; whether the device is *currently being
worn* is not. That is the missing piece behind two open questions: why transparency will
not hold with an earbud in the case, and whether an earbud can be out but not joined.

**Per-earbud identity.** The firmware read returns one version per earbud — the only
field anywhere in this protocol that separates the two. Both currently report the same
version, so it proves the channel exists without yet carrying anything.

**The rest of feature 4.** Roughly thirty operations, mostly uncharacterised: volume,
sidetone, auto-answer, gaming mode, mono downmix, volume limit. Several can be named
without sending a single write, by changing the setting in the vendor application and
re-reading over the wire.

## Known problems

Device behaviour that gets in the way, recorded so the evidence is in one place when
someone has time for it.

### The earbuds get stuck paused

On connecting, the earbuds sometimes come up in a paused state that playback will not
start out of. Observed against a PC and **also against a phone**.

That second detail is what makes this worth writing down: a fault that follows the
device across two unrelated hosts is not a driver problem on either of them, and no
amount of work on the Linux side will fix it.

What the protocol already rules out, or fails to:

- **Wear detection is not the obvious culprit.** The earbuds report on-head detection
  *off* at `0x0401` — remembering that 0 means on there — so a bud that thought it had
  been removed is not the explanation, at least not through that setting.
- **Transparency auto-pause is not it either.** `0x1801` reads *keep playing* on this
  device, and the pauses happen with transparency off.
- **Nothing here can see the media state.** Play and pause travel over standard AVRCP,
  not this protocol, so a desynchronised transport state between host and headset would
  be entirely invisible to everything specified in these documents.

The cheap next step is to catch it in the act: when it happens, read `0x0401` and the
charger state before touching anything, and compare against a healthy connection. If
those match, the fault is in the media transport rather than in anything this library
speaks, and the investigation moves to AVRCP.

## Not planned

Capabilities some devices advertise that are not intended for implementation soon:
renaming, find-device, button mapping, fit test, personalised sound, broadcast audio.
They are real and reachable, but none is specified or verified here, so each is a
research task before it is a feature — listed so their absence stays visible.
