"""Battery level, battery type and charger state.

Feature 3 (``power``). Pure: no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .errors import InvalidLength
from .frame import Frame, MessageType, VENDOR_SENNHEISER

FEATURE_POWER = 3
OP_CHARGER_STATE = 2
OP_BATTERY_LEVEL = 3
OP_BATTERY_TYPES = 14

#: Charger states. There is no case field here even on a model whose battery reading
#: includes the case, so a case percentage does not imply the case reports charging.
CHARGER_STATES: dict[int, str] = {0: "disconnected", 1: "charging", 2: "complete"}

#: Reported as unavailable in the triplet shape. See the warning in :func:`decode_level`.
UNAVAILABLE = 0xFF

#: Hardware battery-type identifiers. These are **not** charge levels.
BATTERY_TYPES: dict[int, str] = {
    0: "micPower",
    1: "vdl",
    2: "varta",
    3: "synergy",
    4: "gp",
    5: "mbt",
    0xFF: "invalid",
}


@dataclass(frozen=True, slots=True)
class BatteryLevel:
    """A battery reading, in one of two shapes.

    Levels are fractions of full charge (``0.7`` is 70%), not percentages.

    ``None`` means *unavailable* — the device declined to report that part. It does not
    mean empty, and it does not reliably mean "in the case".
    """

    shape: Literal["scalar", "triplet"]
    level: float | None = None
    left: float | None = None
    right: float | None = None
    case: float | None = None


def _scale(raw: int) -> float:
    return raw / 100


def decode_level(payload: bytes) -> BatteryLevel:
    """Decode a battery-level payload.

    Two shapes, and they treat ``0xff`` **differently**:

    * **1 byte** — a single level. There is *no* unavailable sentinel in this shape:
      ``0xff`` decodes to ``2.55``. Do not special-case it, and do not clamp it.
    * **3 or more bytes** — left, right, case. Here ``0xff`` *does* mean unavailable
      and becomes ``None``. Bytes beyond the third are not consumed; a field this
      decoder ignores is not proven to be padding.

    Lengths 0 and 2 are rejected, so a truncated triplet cannot be mistaken for a
    scalar.

    Deliberately does not aggregate the three fields into one number. No such rule has
    been established, so any single "headphone %" would be invented. Present the
    fields.
    """
    if len(payload) == 1:
        return BatteryLevel("scalar", level=_scale(payload[0]))
    if len(payload) >= 3:
        return BatteryLevel(
            "triplet",
            left=None if payload[0] == UNAVAILABLE else _scale(payload[0]),
            right=None if payload[1] == UNAVAILABLE else _scale(payload[1]),
            case=None if payload[2] == UNAVAILABLE else _scale(payload[2]),
        )
    raise InvalidLength(f"battery level payload must be 1 or >=3 bytes, got {len(payload)}")


@dataclass(frozen=True, slots=True)
class BatteryTypes:
    """Two independently decoded hardware-type identifiers.

    ``None`` means the value is outside the known set — retained rather than raised,
    because future firmware may add identifiers.

    The physical meaning of the two positions is not established. They are *not*
    left/right, and they are *not* charge levels.
    """

    first: str | None
    second: str | None


def decode_types(payload: bytes) -> BatteryTypes:
    """Decode a battery-types payload. Requires at least two bytes."""
    if len(payload) < 2:
        raise InvalidLength(f"battery types payload must be >=2 bytes, got {len(payload)}")
    return BatteryTypes(BATTERY_TYPES.get(payload[0]), BATTERY_TYPES.get(payload[1]))


def request_level() -> Frame:
    """Build the battery-level request. Empty payload; reads nothing else."""
    return Frame(VENDOR_SENNHEISER, FEATURE_POWER, MessageType.COMMAND, OP_BATTERY_LEVEL)


def request_types() -> Frame:
    """Build the battery-types request. Empty payload."""
    return Frame(VENDOR_SENNHEISER, FEATURE_POWER, MessageType.COMMAND, OP_BATTERY_TYPES)


@dataclass(frozen=True, slots=True)
class ChargerState:
    """Charger state, for one or two positions.

    ``second`` is ``None`` when the device reports a single value. Absence is kept
    distinguishable from *disconnected*: they are different facts.
    """

    first: str | None
    second: str | None = None


def decode_charger(payload: bytes) -> ChargerState:
    """Decode a charger-state reply.

    One byte is a single result; two supply a pair. Further bytes are not consumed.
    An unrecognised value keeps a ``None`` name rather than raising.
    """
    if not payload:
        raise InvalidLength("charger payload is empty")
    return ChargerState(
        CHARGER_STATES.get(payload[0]),
        CHARGER_STATES.get(payload[1]) if len(payload) > 1 else None,
    )


def request_charger() -> Frame:
    """Build the charger-state request. Empty payload."""
    return Frame(VENDOR_SENNHEISER, FEATURE_POWER, MessageType.COMMAND, OP_CHARGER_STATE)
