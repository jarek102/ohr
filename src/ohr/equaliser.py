"""Equaliser: mode, band gains and bass boost.

Two features again. The bands and bass boost are feature 8; the **EQ mode** — which
processing chain is active — is feature 4, not 8. That split is easy to miss.

Gains travel as a **signed byte holding tenths of a decibel**: 30 is +3.0 dB, and 0xF4
is -1.2 dB. Reads only. Pure: no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import InvalidLength
from .frame import Frame, MessageType, VENDOR_SENNHEISER

FEATURE_GENERIC_AUDIO = 4
FEATURE_USER_EQ = 8

OP_MODE = 4
OP_CONFIGURATION = 0
OP_BAND_GAIN = 2
OP_BASS_BOOST = 9

#: Which processing chain is active. Only ``user_eq`` responds to band gains.
MODES: dict[int, str] = {
    0: "off",
    1: "user_eq",
    2: "podcast",
    3: "personalised_sound",
    4: "parametric_eq",
    5: "hearing_enhancement",
}

#: Wire encoding: one signed byte, in tenths of a decibel.
GAIN_STEPS_PER_DB = 10


def _signed(byte: int) -> int:
    return byte - 256 if byte & 0x80 else byte


@dataclass(frozen=True, slots=True)
class Configuration:
    """What the equaliser offers on this device.

    ``trailing`` keeps any bytes past the three understood ones. They are retained
    rather than discarded because a field this decoder ignores is not thereby proven to
    be padding.
    """

    bands: int
    gain_min_db: float
    gain_max_db: float
    trailing: bytes = b""


def request_mode() -> Frame:
    """Which processing chain is active. Empty payload."""
    return Frame(VENDOR_SENNHEISER, FEATURE_GENERIC_AUDIO, MessageType.COMMAND, OP_MODE)


def request_configuration() -> Frame:
    """Band count and gain range. Empty payload."""
    return Frame(
        VENDOR_SENNHEISER, FEATURE_USER_EQ, MessageType.COMMAND, OP_CONFIGURATION
    )


def request_band_gain(index: int) -> Frame:
    """The gain of one band. Payload is the band index."""
    if not 0 <= index <= 0xFF:
        raise ValueError(f"band index out of range: {index}")
    return Frame(
        VENDOR_SENNHEISER,
        FEATURE_USER_EQ,
        MessageType.COMMAND,
        OP_BAND_GAIN,
        bytes([index]),
    )


def request_bass_boost() -> Frame:
    """Is bass boost on? Empty payload."""
    return Frame(VENDOR_SENNHEISER, FEATURE_USER_EQ, MessageType.COMMAND, OP_BASS_BOOST)


def decode_mode(payload: bytes) -> tuple[int, str | None]:
    """Decode an EQ mode reply as ``(value, name)``.

    An unrecognised value keeps a ``None`` name rather than raising — the set of
    processing chains varies by model.
    """
    if not payload:
        raise InvalidLength("eq mode payload is empty")
    return payload[0], MODES.get(payload[0])


def decode_configuration(payload: bytes) -> Configuration:
    """Decode band count and gain limits."""
    if len(payload) < 3:
        raise InvalidLength(
            f"eq configuration payload must be >=3 bytes, got {len(payload)}"
        )
    return Configuration(
        bands=payload[0],
        gain_min_db=_signed(payload[1]) / GAIN_STEPS_PER_DB,
        gain_max_db=_signed(payload[2]) / GAIN_STEPS_PER_DB,
        trailing=payload[3:],
    )


def decode_band_gain(payload: bytes) -> float:
    """Decode a band gain reply, in decibels."""
    if not payload:
        raise InvalidLength("band gain payload is empty")
    return _signed(payload[0]) / GAIN_STEPS_PER_DB


def decode_bass_boost(payload: bytes) -> bool:
    """Decode a bass boost on/off reply."""
    if not payload:
        raise InvalidLength("bass boost payload is empty")
    return payload[0] == 1
