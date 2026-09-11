"""Frame encoding, decoding, and stream reassembly.

Wire format, both directions::

    ff 03 | payload length (u16be) | vendor (u16be) | command word (u16be) | payload

The length field counts **payload bytes only** — it excludes the four bytes of vendor
and command word. Total frame size is therefore ``HEADER_SIZE + length``.

The command word packs three fields::

    feature   = word >> 9
    type      = (word >> 7) & 3
    operation = word & 0x7f

Pure: no I/O, no platform imports. See ``docs/adr/002-layering-and-platform-seams.md``.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from .errors import InvalidValue

START = b"\xff\x03"
HEADER_SIZE = 8

#: Vendor id used by the headsets this package targets.
VENDOR_SENNHEISER = 0x0495


class MessageType(enum.IntEnum):
    """The two-bit type field of the command word."""

    COMMAND = 0
    NOTIFICATION = 1
    RESPONSE = 2
    ERROR = 3


#: Why an :attr:`MessageType.ERROR` reply was sent. One byte, and the two values below
#: are the ones observed — anything else is kept raw rather than guessed at.
ERROR_REASONS: dict[int, str] = {
    0: "feature_not_supported",
    1: "operation_not_supported",
}


def decode_error_reason(payload: bytes) -> tuple[int, str | None]:
    """Decode an error reply's payload as ``(value, name)``.

    The distinction is more useful than it looks. *Feature not supported* and
    *operation not supported* separate "this device cannot do this at all" from "this
    device does this, but not the way you asked" — which makes an error reply a
    **capability probe that does not depend on the feature map**. Asking a device about
    a feature it never advertised returns 0; asking about one it did, with an operation
    it does not have, returns 1.

    An unrecognised value keeps a ``None`` name. The set of reasons a device can give
    is not known to be closed.
    """
    if not payload:
        raise InvalidValue("error reply carried no reason byte")
    return payload[0], ERROR_REASONS.get(payload[0])


def pack_word(feature: int, type: MessageType, operation: int) -> int:
    """Build a command word from its three fields."""
    if not 0 <= feature <= 0x7F:
        raise InvalidValue(f"feature out of range: {feature}")
    if not 0 <= operation <= 0x7F:
        raise InvalidValue(f"operation out of range: {operation}")
    return (feature << 9) | (int(type) << 7) | operation


def unpack_word(word: int) -> tuple[int, MessageType, int]:
    """Split a command word into ``(feature, type, operation)``."""
    if not 0 <= word <= 0xFFFF:
        raise InvalidValue(f"word out of range: {word}")
    return word >> 9, MessageType((word >> 7) & 3), word & 0x7F


@dataclass(frozen=True, slots=True)
class Frame:
    """One complete frame."""

    vendor: int
    feature: int
    type: MessageType
    operation: int
    payload: bytes = b""

    @property
    def word(self) -> int:
        return pack_word(self.feature, self.type, self.operation)

    def to_bytes(self) -> bytes:
        return (
            START
            + len(self.payload).to_bytes(2, "big")
            + self.vendor.to_bytes(2, "big")
            + self.word.to_bytes(2, "big")
            + self.payload
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> Frame:
        """Decode exactly one complete frame.

        For stream data of unknown alignment use :func:`parse_frames` instead.
        """
        if len(data) < HEADER_SIZE:
            raise InvalidValue(f"frame shorter than header: {len(data)} bytes")
        if not data.startswith(START):
            raise InvalidValue(f"bad start marker: {data[:2].hex()}")
        length = int.from_bytes(data[2:4], "big")
        if len(data) != HEADER_SIZE + length:
            raise InvalidValue(
                f"declared length {length} does not match {len(data) - HEADER_SIZE} payload bytes"
            )
        feature, type_, operation = unpack_word(int.from_bytes(data[6:8], "big"))
        return cls(
            vendor=int.from_bytes(data[4:6], "big"),
            feature=feature,
            type=type_,
            operation=operation,
            payload=data[HEADER_SIZE:],
        )

    def matches_reply_to(self, other: Frame) -> bool:
        """Whether this frame is a reply to ``other``.

        Correlation is by vendor, feature and operation — **not** by arrival order.
        Notifications can arrive between a request and its response.

        Note this returns ``True`` for an :attr:`MessageType.ERROR` reply as well as a
        response. An error is a reply; it just is not a success.
        """
        return (
            self.vendor == other.vendor
            and self.feature == other.feature
            and self.operation == other.operation
            and self.type in (MessageType.RESPONSE, MessageType.ERROR)
        )


def parse_frames(buffer: bytes) -> tuple[list[Frame], bytes]:
    """Pull every complete frame out of ``buffer``.

    Returns the frames found and the bytes left over. **A read is not a frame** — a
    single read can end mid-header, carry several frames, or begin mid-stream, so the
    remainder must be carried into the next call.

    Resynchronises on the start marker rather than assuming the buffer begins on a
    frame boundary.
    """
    frames: list[Frame] = []
    while True:
        start = buffer.find(START)
        if start == -1:
            # Keep a trailing 0xff — it may be the first byte of the next marker.
            return frames, buffer[-1:] if buffer.endswith(b"\xff") else b""
        buffer = buffer[start:]
        if len(buffer) < HEADER_SIZE:
            return frames, buffer
        size = HEADER_SIZE + int.from_bytes(buffer[2:4], "big")
        if len(buffer) < size:
            return frames, buffer
        frames.append(Frame.from_bytes(buffer[:size]))
        buffer = buffer[size:]


class FrameStream:
    """Accumulates reads and yields complete frames.

    Convenience over :func:`parse_frames` for callers holding a socket::

        stream = FrameStream()
        for frame in stream.feed(sock.recv(4096)):
            ...
    """

    __slots__ = ("_buffer",)

    def __init__(self) -> None:
        self._buffer = b""

    def feed(self, chunk: bytes) -> list[Frame]:
        self._buffer += chunk
        frames, self._buffer = parse_frames(self._buffer)
        return frames

    @property
    def pending(self) -> bytes:
        """Bytes buffered but not yet a complete frame. Useful in diagnostics."""
        return self._buffer
