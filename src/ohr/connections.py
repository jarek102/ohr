"""Connection management: which devices the headset is paired and connected to.

Feature 10. A headset holds a small number of simultaneous connections across a larger
set of paired devices, so this is how you find out what is currently holding a slot.

**Two command families exist**, selected by the feature's own version: at version 4 and
above, peers are addressed by Bluetooth address; below it, by index. Only the index
family is implemented here, because that is what the devices observed so far report.
Read the feature map at connect time rather than assuming — a firmware update can move
a device across that boundary.

Reads only. Pure: no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import InvalidLength
from .frame import Frame, MessageType, VENDOR_SENNHEISER

FEATURE_DEVICE_MANAGEMENT = 10

OP_PAIRED_COUNT = 0
OP_PEER_DETAILS = 1
OP_OWN_INDEX = 7
OP_MAX_CONNECTIONS = 9

#: Below this version the index-based commands in this module apply.
ADDRESS_VARIANT_MIN_VERSION = 4

#: A field that holds this value is not present rather than zero.
UNAVAILABLE = 0xFF

#: The low two bits of the status byte.
LINK_STATES: dict[int, str] = {
    0: "disconnected",
    1: "classic",
    2: "ble",
    3: "classic_and_ble",
}

#: Bit 7 of the status byte. Not an activity flag — it says the peer is not paired
#: over Classic, which is a different thing from not currently carrying audio.
NO_CLASSIC_PAIRING = 0x80


@dataclass(frozen=True, slots=True)
class Peer:
    """One entry in the headset's list of known devices.

    ``device_type`` is kept raw: no consumer of it has been established, so naming it
    would be invention.

    ``valid`` is false when the headset reports the slot as empty.
    """

    index: int
    device_type: int
    link: str | None
    no_classic_pairing: bool
    name: str
    valid: bool = True

    @property
    def connected(self) -> bool:
        return self.link not in (None, "disconnected")


def request_paired_count() -> Frame:
    """How many devices are paired. Empty payload."""
    return Frame(
        VENDOR_SENNHEISER,
        FEATURE_DEVICE_MANAGEMENT,
        MessageType.COMMAND,
        OP_PAIRED_COUNT,
    )


def request_peer(index: int) -> Frame:
    """Details of one peer. Payload is its index."""
    if not 0 <= index <= 0xFF:
        raise ValueError(f"peer index out of range: {index}")
    return Frame(
        VENDOR_SENNHEISER,
        FEATURE_DEVICE_MANAGEMENT,
        MessageType.COMMAND,
        OP_PEER_DETAILS,
        bytes([index]),
    )


def request_own_index() -> Frame:
    """Which index refers to this host. Empty payload.

    Worth knowing before any future write: disconnecting your own index would destroy
    the channel the undo would need.
    """
    return Frame(
        VENDOR_SENNHEISER, FEATURE_DEVICE_MANAGEMENT, MessageType.COMMAND, OP_OWN_INDEX
    )


def request_max_connections() -> Frame:
    """How many simultaneous connections are supported. Empty payload."""
    return Frame(
        VENDOR_SENNHEISER,
        FEATURE_DEVICE_MANAGEMENT,
        MessageType.COMMAND,
        OP_MAX_CONNECTIONS,
    )


def decode_paired_count(payload: bytes) -> int:
    """Decode the paired-device count."""
    if len(payload) < 2:
        raise InvalidLength(f"paired count payload must be >=2 bytes, got {len(payload)}")
    return int.from_bytes(payload[:2], "big")


def decode_single_byte(payload: bytes, what: str) -> int:
    """Decode a reply carrying one number, such as own index or maximum connections."""
    if not payload:
        raise InvalidLength(f"{what} payload is empty")
    return payload[0]


def decode_peer(payload: bytes) -> Peer:
    """Decode a peer-details reply.

    Layout: index, device type, status, then a name terminated by a zero byte. If any
    of the first three is ``0xff`` the slot is empty, and the result is marked invalid
    rather than being reported as a real device.
    """
    if len(payload) < 3:
        raise InvalidLength(f"peer payload must be >=3 bytes, got {len(payload)}")

    index, device_type, status = payload[0], payload[1], payload[2]
    if UNAVAILABLE in (index, device_type, status):
        return Peer(index, device_type, None, False, "", valid=False)

    raw_name = payload[3:]
    end = raw_name.find(0)
    if end != -1:
        raw_name = raw_name[:end]

    return Peer(
        index=index,
        device_type=device_type,
        link=LINK_STATES[status & 0b11],
        no_classic_pairing=bool(status & NO_CLASSIC_PAIRING),
        name=raw_name.decode("utf-8", errors="replace"),
    )
