"""Equaliser: mode, band gains and bass boost.

Two features again. The bands and bass boost are feature 8; the **EQ mode** — which
processing chain is active — is feature 4, not 8. That split is easy to miss.

Gains travel as a **signed byte holding tenths of a decibel**: 30 is +3.0 dB, and 0xF4
is -1.2 dB. Reads only. Pure: no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass

from .control import Step
from .errors import InvalidLength, InvalidValue
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


# --- writes -----------------------------------------------------------------
#
# Setters acknowledge with an empty payload, so every one of these is sent through
# ohr.control.apply and proved by reading the band back.

OP_SET_BAND_GAIN = 1
OP_SET_BASS_BOOST = 8
OP_SET_MODE = 3

#: Widest gain the wire encoding can carry. **Not** a permissible range: the device
#: reports its own limits in :func:`request_configuration`, and they are narrower on
#: both models observed. Clamp to the device, not to this.
ENCODABLE_DB = 127 / GAIN_STEPS_PER_DB


def request_set_band_gain(index: int, gain_db: float) -> Frame:
    """Set one band's gain. Payload is the band index then a signed gain byte.

    The gain is tenths of a decibel in a signed byte, the same encoding
    :func:`decode_band_gain` reads back.

    **One byte per value is local to this command.** Other writes on this feature
    encode values as unsigned 16-bit, so generalising from here sends half the bytes
    the device expects.
    """
    if not 0 <= index <= 0xFF:
        raise InvalidValue(f"band index out of range: {index}")
    if not -ENCODABLE_DB <= gain_db <= ENCODABLE_DB:
        raise InvalidValue(f"gain {gain_db} dB cannot be encoded in a signed byte")
    steps = round(gain_db * GAIN_STEPS_PER_DB)
    return Frame(
        VENDOR_SENNHEISER,
        FEATURE_USER_EQ,
        MessageType.COMMAND,
        OP_SET_BAND_GAIN,
        bytes([index, steps & 0xFF]),
    )


def request_set_bass_boost(on: bool) -> Frame:
    """Turn bass boost on or off. Payload is one flag byte."""
    return Frame(
        VENDOR_SENNHEISER,
        FEATURE_USER_EQ,
        MessageType.COMMAND,
        OP_SET_BASS_BOOST,
        bytes([1 if on else 0]),
    )


def request_set_mode(mode: int) -> Frame:
    """Select the processing chain. Payload is one byte.

    On **feature 4**, not feature 8 — the mode lives with general audio while the bands
    live with the equaliser, which is the easiest thing to get wrong here.
    """
    if not 0 <= mode <= 0xFF:
        raise InvalidValue(f"eq mode out of range: {mode}")
    return Frame(
        VENDOR_SENNHEISER,
        FEATURE_GENERIC_AUDIO,
        MessageType.COMMAND,
        OP_SET_MODE,
        bytes([mode]),
    )


def _quantised(gain_db: float) -> float:
    """The gain the device will actually hold, given 0.1 dB steps."""
    return round(gain_db * GAIN_STEPS_PER_DB) / GAIN_STEPS_PER_DB


def plan_band_gain(index: int, gain_db: float, configuration: Configuration) -> tuple[Step, ...]:
    """Set one band, verified by reading that band back.

    The configuration is **required, not optional**. The permissible range is whatever
    this device reports, not what the encoding can carry, and the only way to know it is
    to have read it — so the signature makes that a precondition rather than a sentence
    in the documentation.

    Verification compares against the *quantised* value, because the device stores 0.1 dB
    steps and will not read back a request for 3.14 dB unchanged.
    """
    if not 0 <= index < configuration.bands:
        raise InvalidValue(
            f"band {index} does not exist; this device reports {configuration.bands}"
        )
    if not configuration.gain_min_db <= gain_db <= configuration.gain_max_db:
        raise InvalidValue(
            f"gain {gain_db} dB is outside this device's range "
            f"{configuration.gain_min_db} to {configuration.gain_max_db} dB"
        )
    return (
        Step(
            label=f"band {index} = {gain_db:+.1f} dB",
            write=request_set_band_gain(index, gain_db),
            read=request_band_gain(index),
            decode=decode_band_gain,
            expect=_quantised(gain_db),
        ),
    )


def plan_bass_boost(on: bool) -> tuple[Step, ...]:
    """Set bass boost, verified by read-back."""
    return (
        Step(
            label=f"bass boost {'on' if on else 'off'}",
            write=request_set_bass_boost(on),
            read=request_bass_boost(),
            decode=decode_bass_boost,
            expect=on,
        ),
    )


def plan_mode(mode: int) -> tuple[Step, ...]:
    """Select the processing chain, verified by read-back."""
    return (
        Step(
            label=f"eq mode {MODES.get(mode, mode)}",
            write=request_set_mode(mode),
            read=request_mode(),
            decode=lambda payload: decode_mode(payload)[0],
            expect=mode,
        ),
    )


def plan_preset(gains: dict[int, float], configuration: Configuration) -> tuple[Step, ...]:
    """Apply several bands as **one write per band**.

    There is no single command that sets a curve here, so a preset is genuinely N
    writes and **partial application is a real state** — stop halfway and the device is
    holding half of one preset and half of another, which is a shape no preset
    describes. :func:`ohr.control.apply` stops at the first step that does not verify,
    so the caller learns exactly how far it got and can put the rest back.

    Bands are applied in index order, which is arbitrary but fixed: a half-applied
    preset is easier to reason about when the same half applies every time.
    """
    steps: list[Step] = []
    for index in sorted(gains):
        steps.extend(plan_band_gain(index, gains[index], configuration))
    return tuple(steps)
