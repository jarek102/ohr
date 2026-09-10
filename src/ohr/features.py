"""Feature discovery — which capabilities a device advertises, and at what version.

Feature 0 (``core``), operations 1 and 2. Pure: no I/O.

**Discovery is a two-command sequence.** Send :func:`request` (operation 1). If the
reply's :attr:`FeatureList.more` flag is set, send :func:`request_continuation`
(operation 2) and :func:`merge` the two. A client that issues only operation 2, or
ignores the flag, can end up with a partial map — and since the map decides which
connection-command family a device uses, a partial map can select the wrong one.

On the names: the **ids and versions are what the device reports**. The names in
:data:`FEATURE_NAMES` are our own descriptive labels for readability and are not part
of the wire protocol. Where the two disagree, the id wins. See
``docs/protocol/provenance.md``.
"""

from __future__ import annotations

from dataclasses import dataclass

from .frame import Frame, MessageType, VENDOR_SENNHEISER

FEATURE_CORE = 0
OP_FEATURE_LIST = 1
OP_FEATURE_LIST_CONTINUATION = 2

#: Descriptive labels for observed feature ids. Not wire data.
FEATURE_NAMES: dict[int, str] = {
    0: "core",
    1: "upgrade_extension",
    2: "device",
    3: "power",
    4: "generic_audio",
    6: "earbud",
    8: "user_eq",
    9: "versions",
    10: "device_management",
    11: "mmi_config",
    12: "transparent_hearing",
    13: "anc",
    14: "tws",
    15: "fitting_test",
    16: "personalized_sound",
    17: "sensor",
    18: "mcu_info",
    19: "tap_detection",
    20: "local_name",
    21: "auracast",
    22: "find_device",
    23: "hearing_enhancement",
    24: "device_ui",
    25: "transmitter_input_source",
    26: "auracast_transmitter",
    27: "spatial_audio",
    28: "transmitter_syncer",
}

#: Feature 10 at or above this version uses address-based connection commands;
#: below it, index-based. Both currently known devices report below it.
DEVICE_MANAGEMENT_ADDRESS_VARIANT_MIN = 4


@dataclass(frozen=True, slots=True)
class FeatureEntry:
    """One advertised feature. ``name`` is ``None`` for ids we have no label for."""

    id: int
    name: str | None
    version: int


@dataclass(frozen=True, slots=True)
class FeatureList:
    """A decoded feature map.

    ``more`` set means the device has further entries and a continuation request is
    required.
    """

    more: bool
    features: tuple[FeatureEntry, ...]

    def version_of(self, feature_id: int) -> int | None:
        """Version the device reports for ``feature_id``, or ``None`` if absent."""
        for entry in self.features:
            if entry.id == feature_id:
                return entry.version
        return None

    def supports(self, feature_id: int) -> bool:
        return self.version_of(feature_id) is not None


def decode(payload: bytes) -> FeatureList:
    """Decode a feature-list payload.

    An empty payload is **valid**: no continuation, no features.

    Otherwise byte 0 is the continuation flag — true only when it **equals 1**, not
    merely when non-zero — and the rest is ``(id, version)`` pairs. An unpaired
    trailing byte is dropped rather than treated as a version of zero.

    Unrecognised ids are kept with a ``None`` name. Discarding them would understate
    what a device supports as firmware adds capabilities.
    """
    if not payload:
        return FeatureList(False, ())
    body = payload[1:]
    return FeatureList(
        more=payload[0] == 1,
        features=tuple(
            FeatureEntry(body[i], FEATURE_NAMES.get(body[i]), body[i + 1])
            for i in range(0, len(body) - 1, 2)
        ),
    )


def merge(first: FeatureList, second: FeatureList) -> FeatureList:
    """Combine an initial reply with its continuation.

    Entries from ``first`` win on duplicate ids. The result's ``more`` flag is the
    continuation's, so a caller can loop until it clears.
    """
    seen = {entry.id for entry in first.features}
    extra = tuple(e for e in second.features if e.id not in seen)
    return FeatureList(second.more, first.features + extra)


def request() -> Frame:
    """Build the initial feature-list request. Empty payload."""
    return Frame(VENDOR_SENNHEISER, FEATURE_CORE, MessageType.COMMAND, OP_FEATURE_LIST)


def request_continuation() -> Frame:
    """Build the continuation request. Send **only** when ``more`` is set."""
    return Frame(
        VENDOR_SENNHEISER, FEATURE_CORE, MessageType.COMMAND, OP_FEATURE_LIST_CONTINUATION
    )
