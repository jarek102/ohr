# Framing

Every frame, in both directions:

```
ff 03 | payload length (u16be) | vendor (u16be) | command word (u16be) | payload
```

| Field | Size | Notes |
|---|---|---|
| Start marker | 2 | Always `ff 03` |
| Payload length | 2 | Big-endian. **Payload bytes only** — excludes vendor and word |
| Vendor | 2 | `0x0495` for the devices covered here |
| Command word | 2 | Big-endian; see below |
| Payload | *length* | May be empty |

Total frame size is `8 + length`. The length field excluding the vendor and word
fields is the detail most likely to be got wrong; a decoder that includes them reads
four bytes too many and desynchronises.

## The command word

Three packed fields:

```
feature   = word >> 9
type      = (word >> 7) & 3
operation = word & 0x7f
```

| Type | Meaning |
|---|---|
| 0 | command |
| 1 | notification |
| 2 | response |
| 3 | error |

So a request with feature 3, operation 3 is word `0x0603`; its response is `0x0703`
and an error carrying the same feature and operation is `0x0783`.

### Worked example

The battery request, and the reply from an over-ear device:

```
ff03 0000 0495 0603              request,  no payload
ff03 0001 0495 0703 46           response, one payload byte
```

The reply's length is `0x0001` — one payload byte, `0x46` — and the word `0x0703`
unpacks to feature 3, type 2 (response), operation 3.

## Reading from a stream

**A read is not a frame.** The transport is a byte stream, so one read can:

- end part-way through the header, before the length is even known;
- end part-way through a payload;
- contain several complete frames;
- begin part-way through a frame, if synchronisation was lost.

An implementation must buffer, resynchronise on the `ff 03` marker, and carry the
remainder into the next read. The `stream` vectors in
[`vectors/framing.json`](../../vectors/framing.json) cover each of these cases; an
implementation that passes only the `frame` vectors is not finished.

## Correlating replies

Match a reply to its request by **vendor, feature and operation** — never by arrival
order. Notifications may arrive between a request and its response, and a device may
answer out of order.

An **error is a reply**. A type-3 frame with the matching feature and operation is the
answer to the request; it just is not a success. Treat it as *state unknown, re-read*,
not as a failure to transmit.

### The reason byte

An error payload is one byte:

| Value | Meaning |
|---|---|
| 0 | feature not supported |
| 1 | operation not supported |

That distinction makes an error frame a **capability probe that does not depend on the
feature map**. Ask about a feature a device never advertised and it answers 0; ask about
one it did advertise, with an operation it does not have, and it answers 1.

Both models were sent nonsense operations on features 0, 12 and 13, and both answered 1
every time. Sent the same request on feature 30, which neither advertises, both
answered 0. Sent it on feature 14, the earbuds answered 1 and the over-ear model 0 —
matching exactly which of them lists that feature. The reason agrees with the feature
map without being read from it.

Unrecognised values are kept raw: the set of reasons is not known to be closed.

### Silence is not the same as "not supported"

Sweeping all 128 feature numbers on both models, with an operation established as
unused everywhere, splits them cleanly in two:

| Feature | Behaviour |
|---|---|
| 0–31 | answers, with reason 0 or 1 |
| 32–127 | **no reply at all** |

So the feature field is seven bits wide but only the low five are live on these
devices. Beyond 31 nothing comes back — not an error, nothing — and a client waits out
its whole timeout for each one.

Which is the practical point: **a timeout is not evidence that something is
unsupported.** A device that lacks a feature says so, in about a millisecond. One that
says nothing is either out of range, wedged, or busy — and at least one model here is
known to ignore a first request and answer a retry.

### Does control traffic degrade the audio? Measured: not by codec

Stop a sweep at 31 — most of a full sweep is time spent waiting out features that do not
exist.

A stronger claim used to sit here. The sweep that established that boundary held the
channel for about two minutes and **was followed by an audible drop in quality that a
reconnect cleared**, which looks exactly like a codec renegotiating downwards under
contention. Once `0x0800` was found, that became testable.

It did not reproduce, on either model, with a steady stream and the codec sampled
throughout by both the device and the host stack:

| Model | Load | Result |
|---|---|---|
| over-ear | 4,282 answered reads in 100 s (~43/s) | `aptx_hd` throughout |
| over-ear | 110 *unanswered* requests over 110 s | `aptx_hd` throughout |
| earbuds | both at once — unanswered requests interleaved with saturating reads | `aptx` throughout |

The unanswered-request runs are the important ones. The original sweep was not high
throughput: two thirds of it was aimed at features above 31, so the channel spent most
of its time holding one unanswered request open. That is a different stressor from
saturation, and reproducing its shape changed nothing either.

The earbuds had somewhere to fall, which is worth confirming rather than assuming. Their
host offers SBC, SBC-XQ, AAC and aptX, and aptX — the highest priority of the four — was
active before, during and after. They were not already sitting in a degraded state with
no room to drop further.

**These runs never reproduced the fault**, which is the first thing to say. The audio
was fine throughout all of them, so what they measured was a healthy link under load —
not the thing worth understanding.

The original event, described properly, is a different animal:

| | |
|---|---|
| Symptom | choppy and badly degraded — a **dropout** signature, not a quieter or coarser stream |
| Duration | **persisted after the traffic stopped**, indefinitely |
| Cleared by | reconnecting — and, on at least one occasion, by **switching the codec** |

Persistence is the decisive detail. Congestion ends when the load does; this did not. So
whatever went wrong was not contention while the burst ran but **a state the link got
into and stayed in**, and the fix both times was the same thing underneath: tearing down
the audio stream and setting it up again. Changing the codec does that as a side effect,
which is why it worked.

That also explains why a codec read found nothing. The codec never was the variable —
it stays put across the fault, which is exactly why switching it *deliberately* is an
effective repair rather than a diagnosis.

**Practical consequence.** If audio degrades during heavy control traffic, it will not
recover on its own. Re-establish the stream. On a PipeWire host, switching the card to
another A2DP codec and back does that in a few seconds, without unpairing or power
cycling anything:

```bash
pactl list short cards | grep bluez
```

```bash
pactl set-card-profile bluez_card.AA_BB_CC_DD_EE_FF a2dp-sink-aac && sleep 2 && pactl set-card-profile bluez_card.AA_BB_CC_DD_EE_FF a2dp-sink
```

Checked on the earbuds: the profile moved to AAC and back, and the negotiated codec
returned to aptX. Substitute whichever profiles that card offers — `pactl list cards`
names them, and they differ per device.

**Still unexplained**, and not answerable with this protocol: what stuck, and why. The
useful experiment is no longer "watch the codec under load" but "reproduce the fault,
then compare host-side packet statistics against a healthy link" — retransmissions,
buffer underruns, flush timeouts.

## Writes

No setter in this protocol returns meaningful state. Setters reply with an
acknowledgement carrying no payload, so **a successful write is not evidence that
anything changed.** Read back the corresponding getter to confirm.

Some user-visible operations are also **sequences of several commands** with awaits
between them, which means a partially applied state is real and reachable. Capture
state before such a sequence and verify after it.
