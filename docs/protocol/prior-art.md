# Prior art

Other people have worked on this protocol. Their work is useful here in one specific
way: as a **source of hypotheses**, never as a source of facts.

That is not a slight. It follows from the rule the rest of this specification is built
on — a claim enters it when a device has been seen to do the thing, with a vector to
match ([evidence](provenance.md)). A claim in somebody else's repository is evidence
that *they* believe something, which is worth a great deal when it disagrees with us and
nothing at all as a citation.

## What exists

| | | |
|---|---|---|
| [f3Y0/momentum4-control](https://github.com/f3Y0/momentum4-control) | Python, PyQt6, MIT | Tray controller for the MOMENTUM 4. States plainly that it is AI-generated and unreviewed. |
| [zaval/sennheiser-desktop-client](https://github.com/zaval/sennheiser-desktop-client) | C++/Qt 6 | Desktop client for the same model; generates its protocol classes from JSON schemas. |
| [Ethical hacking of Sennheiser smart headphones](https://kth.diva-portal.org/smash/get/diva2:1749924/FULLTEXT01.pdf) | KTH thesis | Security analysis rather than a control implementation. |

Both projects target the **MOMENTUM 4**, which is neither of the models tested here.
Where they disagree with observation, "different model" is a live explanation and not
an excuse.

## Where it agrees

Independent agreement is worth more than the count of sources suggests, because these
were arrived at separately:

- **The service UUID** `a2129ff3-081b-4c45-8afe-469d9c4842ec`, exactly.
- **Vendor `0x0495`**, the `ff 03` start marker, and a header of start, big-endian
  payload length, vendor, command word.
- **A response is the request with the type bits raised.** They compute it as
  `command | 0x0100`, which is the same arithmetic as setting the two-bit type field to
  2 — see [framing](framing.md).
- **`0x1a04` / `0x1a05` set and get ANC**, one flag byte.
- **`0x1008` / `0x1009` set and get bass boost.**
- **Service discovery does not work.** They do not resolve the channel by UUID either;
  they connect to a hard-coded list of candidate channels and keep whichever answers.
  This was the most surprising finding of M1 and it is now independently corroborated.

## Where it conflicts — and this one matters

They label `0x1a02` / `0x1a03` **transparency**, and treat it as a single blended axis:

```
ui  +100  (full ANC)          ->  wire 0
ui     0                      ->  wire 50
ui  -100  (full transparency) ->  wire 100
```

Their control writes ANC on, then writes that byte. **It never touches feature 12 at
all** — no `0x1804`, no `0x1805`.

This specification says something different: that `0x1a03` reports the ANC level while
transparency is off and full scale while it is on, and that transparency is a separate
feature with its own flag and its own level at `0x1803`.

**Their model explains the observations here at least as economically as ours does.**
Every reading taken so far fits it:

| Observed | Our reading | Their reading |
|---|---|---|
| transparency on → `0x1a03` reads 100 | full scale, reason unknown | the axis is at full transparency |
| ANC on, transparency off → reads 0 | the stored ANC level | the axis is at full ANC |
| writing `0x1a02` clears the transparency flag | a side effect of engaging ANC | the flag *is* "axis at 100", so writing 40 clears it |
| both flags read on together | two independent flags | ANC enabled, axis at 100 |

Ours needs two flags, two levels and a one-way coupling. Theirs needs one axis and an
enable, with `0x1805` a view of the axis rather than a thing of its own. The second is
the better story, and being the better story is not evidence.

### Settled: it does not hold here

The experiment was to drive the level from each starting position on the over-ear model
and listen. The deciding case turned out not to be the obvious one:

> **With transparency on and ANC off, writing *any* level — including 100 — drops the
> device to off.**

A command meaning *full transparency* cannot leave you with no transparency. And the
flag agrees without anyone listening: `0x1805` reads 0 after a level write, whatever
value was written, so the flag is not a view of an axis sitting at its transparency end.

Every case follows instead from the plainer rule — **the write clears the transparency
flag and leaves ANC alone**:

| Before | Heard | Under "clears transparency" |
|---|---|---|
| ANC on, transparency off | stays ANC, level applies | nothing to clear |
| both off | nothing | nothing to clear, ANC already off |
| transparency on, ANC off | drops to off | flag cleared, ANC was off |
| transparency on, ANC on | drops to ANC | flag cleared, ANC stays |

Two loose ends, neither of which rescues the axis. With ANC on, levels 0 and 100 produce
a short tone and values between them do not — the endpoints act like a state change.
And no difference in cancelling was reported between those endpoints, judged in a quiet
room, which is the weakest observation in this document.

**The blend reading may still be correct for the MOMENTUM 4.** It is a model neither of
us has. What is settled is that it does not describe these two.

### Worth saying about how it went

That hypothesis was worth the day it cost. It was simpler than ours, it fitted every
reading we had, and the only way to separate them was to go and ask — which produced a
better-specified command than the one we started with, including a behaviour table
nobody would have thought to capture without something to disprove.

It also survives as the explanation for `0x1803` being unaccounted for in their model:
that read differs between our two devices, 100 against 75, and is unmoved by mode. An
axis has no room for it.

## What they have that is not here

- **`0x0007` registers for notifications**, payload one feature byte. That is feature 0,
  operation **7** — an odd operation that writes, which is one more reason parity says
  nothing about what is safe to send. Relevant to event subscription, which is M8.

## What is here that they do not do

Recorded because the difference is instructive, not as a scoreboard:

- **They do not read back.** A write is sent and the new state assumed. Every device
  here has been seen to acknowledge a setting and not have it: an empty acknowledgement
  is not evidence, and one model confirmed a transparency write and abandoned it a
  second later.
- **They ship channel numbers.** A hard-coded candidate list works until firmware moves,
  and a wrong guess connects to some other service.
- **No error reason.** An error reply carries a byte saying whether the *feature* or the
  *operation* was missing, which is how a client tells "this device cannot" from "I
  asked wrongly".

## The rule

Read prior art. Take its hypotheses seriously, especially where they are simpler than
yours. Then go and ask a device, because that is the only thing that settles anything —
and write down what it said, not what you expected.
