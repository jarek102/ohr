"""Feature 4 settings: the negotiated codec, and the device's own prompts.

Feature 4 is the general audio feature, and it is large — the equaliser *mode* lives
here too, which is why :mod:`ohr.equaliser` reaches into it. Only the commands
confirmed on hardware are here.

Its layout is the opposite of noise control's: **the setter sits one below its
getter**, so the even operations read and the odd ones write. Features 12 and 13 do it
the other way round. There is no rule; check each feature.

Pure: no I/O. Reads only.
"""

from __future__ import annotations

from .errors import InvalidLength, InvalidValue
from .frame import Frame, MessageType, VENDOR_SENNHEISER

FEATURE_GENERIC_AUDIO = 4

OP_CODEC = 0
OP_PROMPTS = 2
OP_PROMPT_LANGUAGE = 7

#: What the audio link negotiated. The high values are states rather than codecs.
CODECS: dict[int, str] = {
    0: "sbc",
    1: "aac",
    2: "aptx",
    3: "aptx_ll",
    4: "mp3",
    5: "aptx_hd",
    6: "faststream",
    7: "lhdc",
    8: "aptx_adaptive",
    9: "aptx_lossless",
    10: "lc3",
    11: "usb",
    12: "aptx_voice",
    13: "aptx_lite",
    14: "lc3_gaming",
    240: "call_ongoing",
    254: "unknown",
    255: "no_stream",
}

#: Whether the device makes a sound when something changes.
PROMPTS: dict[int, str] = {0: "off", 1: "tones_only", 2: "tones_and_voice"}

#: Language of the spoken prompts.
PROMPT_LANGUAGES: dict[int, str] = {
    0: "english",
    1: "german",
    2: "french",
    3: "spanish",
    4: "chinese",
    5: "japanese",
    6: "russian",
}


def request_codec() -> Frame:
    """The codec currently negotiated for audio. Empty payload."""
    return Frame(
        VENDOR_SENNHEISER, FEATURE_GENERIC_AUDIO, MessageType.COMMAND, OP_CODEC
    )


def request_prompts() -> Frame:
    """Whether tones and voice prompts are enabled. Empty payload."""
    return Frame(
        VENDOR_SENNHEISER, FEATURE_GENERIC_AUDIO, MessageType.COMMAND, OP_PROMPTS
    )


def request_prompt_language() -> Frame:
    """Which language the spoken prompts use. Empty payload."""
    return Frame(
        VENDOR_SENNHEISER,
        FEATURE_GENERIC_AUDIO,
        MessageType.COMMAND,
        OP_PROMPT_LANGUAGE,
    )


def decode_codec(payload: bytes) -> tuple[int, str | None]:
    """Decode a codec reply as ``(value, name)``.

    **This is live state, not a capability.** With nothing playing both observed models
    answer 255, *no stream* — so a client must not read it once at connect time and
    treat the answer as what the device supports.

    Two of the values are not codecs at all: 240 says a call is in progress and 254 says
    the device does not know. Keeping them in the same field means a caller that maps
    this straight to a label will happily print "call ongoing" as a codec name.

    An unrecognised value keeps a ``None`` name rather than raising; the list grows with
    firmware.
    """
    if not payload:
        raise InvalidLength("codec payload is empty")
    return payload[0], CODECS.get(payload[0])


def decode_prompts(payload: bytes) -> tuple[int, str | None]:
    """Decode the prompt setting as ``(value, name)``.

    Worth reading before writing anything. Several setters in this protocol are
    **audible** — the ANC flag on both observed models, submodes on one, transparency on
    the other — and this says whether the device will actually make that sound. It turns
    "a write may be heard" from a permanent caveat into something a client can check.
    """
    if not payload:
        raise InvalidLength("prompts payload is empty")
    if payload[0] not in PROMPTS:
        raise InvalidValue(f"prompt setting {payload[0]} is not a known value")
    return payload[0], PROMPTS[payload[0]]


def decode_prompt_language(payload: bytes) -> tuple[int, str | None]:
    """Decode the prompt language as ``(value, name)``.

    Unknown values keep a ``None`` name: a device shipped with a language this list does
    not have is not a malformed reply.
    """
    if not payload:
        raise InvalidLength("prompt language payload is empty")
    return payload[0], PROMPT_LANGUAGES.get(payload[0])
