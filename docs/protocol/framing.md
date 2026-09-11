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

### The control channel is not free

Stop a sweep at 31. Beyond the wasted time, the sweep that established the boundary
above held the channel for about two minutes, and **the audio noticeably degraded while
it ran** — cleared by disconnecting and reconnecting, which is what a codec
renegotiating downwards under contention would look like.

Control traffic and the audio link share a radio. Probe when nothing is playing, keep
routine polling modest, and treat a burst of requests as something with a cost to the
person listening rather than a free way to learn about the device.

## Writes

No setter in this protocol returns meaningful state. Setters reply with an
acknowledgement carrying no payload, so **a successful write is not evidence that
anything changed.** Read back the corresponding getter to confirm.

Some user-visible operations are also **sequences of several commands** with awaits
between them, which means a partially applied state is real and reachable. Capture
state before such a sequence and verify after it.
