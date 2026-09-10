"""Noise control: ANC, transparency, submodes and level.

Two features, not one. ANC is feature 13; transparency (letting outside sound through)
is feature 12, with its own commands. The user-facing choice between *ANC*,
*Transparency* and *Off* is a combination of the two, not a single setting — which is
why writing a mode is a sequence rather than one command.

Reads only. Pure: no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import InvalidLength, InvalidValue
from .frame import Frame, MessageType, VENDOR_SENNHEISER

FEATURE_TRANSPARENT_HEARING = 12
FEATURE_ANC = 13

OP_SUBMODES = 1
OP_LEVEL = 3
OP_ENABLED = 5

#: Submode identifiers. Availability differs by model.
SUBMODES: dict[int, str] = {1: "anti_wind", 2: "comfort", 3: "adaptive"}


def _flag(payload: bytes, what: str) -> bool:
    if not payload:
        raise InvalidLength(f"{what} payload is empty")
    if payload[0] > 1:
        raise InvalidValue(f"{what} state {payload[0]} is neither off nor on")
    return payload[0] == 1


@dataclass(frozen=True, slots=True)
class Submode:
    """One submode and its current setting.

    ``state`` is left raw: anti-wind is known to take three values while the others
    take two, and nothing here assumes which model supports what.
    """

    id: int
    name: str | None
    state: int


def request_enabled() -> Frame:
    """Is ANC on? Empty payload."""
    return Frame(VENDOR_SENNHEISER, FEATURE_ANC, MessageType.COMMAND, OP_ENABLED)


def request_transparency() -> Frame:
    """Is transparency on? Empty payload."""
    return Frame(
        VENDOR_SENNHEISER, FEATURE_TRANSPARENT_HEARING, MessageType.COMMAND, OP_ENABLED
    )


def request_submodes() -> Frame:
    """Which submodes exist and how they are set. Empty payload."""
    return Frame(VENDOR_SENNHEISER, FEATURE_ANC, MessageType.COMMAND, OP_SUBMODES)


def request_level() -> Frame:
    """The ANC/transparency level. Empty payload."""
    return Frame(VENDOR_SENNHEISER, FEATURE_ANC, MessageType.COMMAND, OP_LEVEL)


def decode_enabled(payload: bytes) -> bool:
    """Decode an ANC on/off reply."""
    return _flag(payload, "anc enabled")


def decode_transparency(payload: bytes) -> bool:
    """Decode a transparency on/off reply."""
    return _flag(payload, "transparency")


def decode_level(payload: bytes) -> float:
    """Decode a level reply as a fraction of full scale."""
    if not payload:
        raise InvalidLength("level payload is empty")
    return payload[0] / 100


def decode_submodes(payload: bytes) -> tuple[Submode, ...]:
    """Decode submodes as ``(identifier, state)`` pairs.

    An odd-length payload is rejected: a trailing identifier with no state would
    otherwise be read as a submode set to zero.

    Unknown identifiers are kept with a ``None`` name rather than dropped.
    """
    if len(payload) % 2:
        raise InvalidLength(
            f"submodes payload must be pairs, got {len(payload)} bytes"
        )
    return tuple(
        Submode(payload[i], SUBMODES.get(payload[i]), payload[i + 1])
        for i in range(0, len(payload), 2)
    )
