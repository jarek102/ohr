"""Device identity and physical state: versions, product name, on-head detection.

Two features. Feature 9 answers *what is this and what is it running*; feature 2 carries
the on-head detection setting. Neither changes anything — every command here is a read.

Pure: no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import InvalidLength, InvalidValue
from .frame import Frame, MessageType, VENDOR_SENNHEISER

FEATURE_DEVICE = 2
FEATURE_VERSIONS = 9
FEATURE_LOCAL_NAME = 20

OP_ON_HEAD_DETECTION = 1
OP_VERSION_WIDE = 1
OP_VERSION = 2
OP_CASE_SERIAL = 5
OP_PRODUCT_NAME = 6
OP_LOCAL_NAME = 2
OP_APTX_96K = 6
OP_APTX_LOSSLESS = 8


@dataclass(frozen=True, slots=True)
class Version:
    """A three-part version."""

    major: int
    minor: int
    patch: int

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


def _triple(payload: bytes, start: int) -> Version:
    return Version(payload[start], payload[start + 1], payload[start + 2])


def request_version() -> Frame:
    """Firmware version. Empty payload."""
    return Frame(VENDOR_SENNHEISER, FEATURE_VERSIONS, MessageType.COMMAND, OP_VERSION)


def request_version_wide() -> Frame:
    """The same firmware version in a wider encoding. Empty payload.

    Kept because it is a free cross-check: two commands that must agree are worth more
    than either alone when a decoder is being written from scratch.
    """
    return Frame(VENDOR_SENNHEISER, FEATURE_VERSIONS, MessageType.COMMAND, OP_VERSION_WIDE)


def request_product_name() -> Frame:
    """Product name and finish, as text. Empty payload."""
    return Frame(
        VENDOR_SENNHEISER, FEATURE_VERSIONS, MessageType.COMMAND, OP_PRODUCT_NAME
    )


def request_case_serial() -> Frame:
    """Charging-case serial number. Empty payload."""
    return Frame(
        VENDOR_SENNHEISER, FEATURE_VERSIONS, MessageType.COMMAND, OP_CASE_SERIAL
    )


def request_local_name() -> Frame:
    """The device's own Bluetooth name. Empty payload.

    **Operation 2, not 0.** Operation 0 on this feature answers with an empty payload,
    which is indistinguishable from a setter acknowledging — so it is not used here and
    not specified as a read.
    """
    return Frame(
        VENDOR_SENNHEISER, FEATURE_LOCAL_NAME, MessageType.COMMAND, OP_LOCAL_NAME
    )


def decode_local_name(payload: bytes) -> str:
    """Decode the device name.

    Unlike the product name this is **whatever the owner called it**, so treat it as
    their data: show it, do not publish it.
    """
    return payload.split(b"\x00", 1)[0].decode("utf-8", errors="replace")


def request_aptx_96k_support() -> Frame:
    """Is the 96 kHz aptX mode enabled? Empty payload."""
    return Frame(VENDOR_SENNHEISER, FEATURE_DEVICE, MessageType.COMMAND, OP_APTX_96K)


def decode_aptx_96k_support(payload: bytes) -> bool:
    """Decode the 96 kHz aptX setting. Normal polarity: 0 is off.

    Two operations away from on-head detection, which is inverted. Decode each command
    against its own meaning; this feature does not have one convention.
    """
    if not payload:
        raise InvalidLength("aptx 96k payload is empty")
    if payload[0] > 1:
        raise InvalidValue(f"aptx 96k value {payload[0]} is neither off nor on")
    return payload[0] == 1


def request_aptx_lossless_support() -> Frame:
    """Is the lossless aptX mode enabled? Empty payload.

    **Only the earbuds answer.** The over-ear model advertises the same feature and
    replies *operation not supported* to this one — so a feature map that lists a
    feature does not promise every operation inside it. Capability is per command.
    """
    return Frame(VENDOR_SENNHEISER, FEATURE_DEVICE, MessageType.COMMAND, OP_APTX_LOSSLESS)


def decode_aptx_lossless_support(payload: bytes) -> bool:
    """Decode the lossless aptX setting. Normal polarity: 0 is off."""
    return decode_aptx_96k_support(payload)


def request_on_head_detection() -> Frame:
    """Whether on-head detection is switched on. Empty payload."""
    return Frame(
        VENDOR_SENNHEISER, FEATURE_DEVICE, MessageType.COMMAND, OP_ON_HEAD_DETECTION
    )


def decode_versions(payload: bytes) -> tuple[Version, ...]:
    """Decode a firmware version reply as one version per three bytes.

    Both observed models answer with **six** bytes, not three. The earbuds return the
    same version twice, one per bud; the over-ear model returns its version followed by
    three zero bytes. So a second triple is not evidence of a second component — check
    whether it is zero before showing it.

    A decoder that read only the first three bytes would be right about the version and
    blind to the per-bud field, which is the only place these two earbuds are
    distinguished from each other anywhere in this protocol.
    """
    if len(payload) < 3:
        raise InvalidLength(f"version payload must be >=3 bytes, got {len(payload)}")
    return tuple(
        _triple(payload, start) for start in range(0, len(payload) - 2, 3)
    )


def decode_version_wide(payload: bytes) -> Version:
    """Decode the wide version encoding: three 16-bit big-endian fields."""
    if len(payload) < 6:
        raise InvalidLength(f"wide version payload must be >=6 bytes, got {len(payload)}")
    return Version(
        int.from_bytes(payload[0:2], "big"),
        int.from_bytes(payload[2:4], "big"),
        int.from_bytes(payload[4:6], "big"),
    )


def decode_product_name(payload: bytes) -> str:
    """Decode the product name, which is NUL-terminated.

    This is the model and its finish — a property of the product, not of the owner.
    """
    return payload.split(b"\x00", 1)[0].decode("utf-8", errors="replace")


def decode_case_serial(payload: bytes) -> bytes:
    """Return the charging-case serial as raw bytes.

    Deliberately **not** formatted into a string. It is four bytes whose structure is
    not established, and it identifies one physical object belonging to one person — so
    it is handed back as bytes for a caller that has a reason to want it, rather than
    rendered somewhere it might be shown or logged.

    A model with no case answers with zeroes rather than refusing.
    """
    if len(payload) < 4:
        raise InvalidLength(f"case serial must be >=4 bytes, got {len(payload)}")
    return bytes(payload[:4])


def decode_on_head_detection(payload: bytes) -> bool:
    """Decode the on-head detection setting.

    **The polarity is inverted.** Zero means *on* here, where every other flag in this
    protocol uses zero for off. That is not a guess: the earbuds report 1 while the
    vendor application shows their equivalent setting switched off.

    Returns ``True`` when the feature is enabled, so callers never see the inversion —
    but anyone reading raw payloads will, and it is the sort of thing that silently
    inverts a switch in a user interface.
    """
    if not payload:
        raise InvalidLength("on-head detection payload is empty")
    if payload[0] > 1:
        raise InvalidValue(
            f"on-head detection value {payload[0]} is neither on nor off"
        )
    return payload[0] == 0
