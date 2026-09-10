"""Vendor control protocol for Sennheiser Bluetooth headsets over RFCOMM.

An unofficial, independently developed implementation. Not affiliated with or endorsed
by the manufacturer.

This package is pure and portable: framing and payload codecs with no I/O, no platform
imports, and no GUI toolkit. Platform backends satisfy :mod:`ohr.transport` and
:mod:`ohr.lease`; a Linux service layer ships as the ``service`` extra.

Correctness is defined by ``vectors/`` — language-neutral fixtures that any
implementation, in any language, must reproduce.

Typical read::

    from ohr import battery, frame

    request = battery.request_level()
    conn.send(request.to_bytes(), timeout=5.0)

    stream = frame.FrameStream()
    for reply in stream.feed(conn.receive(timeout=5.0)):
        if reply.matches_reply_to(request):
            level = battery.decode_level(reply.payload)

Writes are a different matter. No write in this protocol returns a meaningful
acknowledgement — setters reply with an empty acknowledgement that carries no state —
so a successful write is not evidence that anything changed. Read back.
"""

from __future__ import annotations

from .errors import DeviceBusy, InvalidLength, InvalidValue, ProtocolError
from .frame import (
    HEADER_SIZE,
    START,
    VENDOR_SENNHEISER,
    Frame,
    FrameStream,
    MessageType,
    pack_word,
    parse_frames,
    unpack_word,
)

__version__ = "0.0.1"

__all__ = [
    "DeviceBusy",
    "Frame",
    "FrameStream",
    "HEADER_SIZE",
    "InvalidLength",
    "InvalidValue",
    "MessageType",
    "ProtocolError",
    "START",
    "VENDOR_SENNHEISER",
    "__version__",
    "pack_word",
    "parse_frames",
    "unpack_word",
]
