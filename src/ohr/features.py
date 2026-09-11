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

from .errors import InvalidValue
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


#: Feature numbers above this answer nothing at all on the observed devices — not an
#: error, no reply. The field is seven bits wide; only the low five are live.
HIGHEST_ANSWERING_FEATURE = 31

#: An operation that exists on no feature of either observed device, which is what
#: makes it usable as a probe: the reply can only be an error, so its reason byte
#: reports whether the *feature* is there and nothing else happens.
PROBE_OPERATION = 0x7F


def request_capability_probe(feature: int) -> Frame:
    """Ask whether a device has ``feature``, without reading anything from it.

    The reply is always an :attr:`MessageType.ERROR`; decode its payload with
    :func:`ohr.frame.decode_error_reason`. Reason 1 — *operation not supported* — means
    the feature is there. Reason 0 means it is not.

    This exists because the answer does not depend on the feature map, so it can check
    the map rather than trusting it. Both observed devices agreed exactly, which is the
    result that makes the map worth trusting in the first place.

    **The operation is chosen, not defined.** It was confirmed unused on every feature
    either device implements, and a firmware that gave it a meaning would turn this
    from a question into a command. Re-confirm before relying on it against hardware
    this was not checked on, and prefer the feature map for ordinary use.

    Feature numbers above :data:`HIGHEST_ANSWERING_FEATURE` do not answer at all, so a
    sweep over the whole seven-bit range spends most of its time waiting for timeouts
    that mean nothing. **Stop at 31.**

    That is not only about speed. A full sweep with a one-second timeout holds the
    control channel for roughly two minutes, and running one while audio was playing
    was followed by an audible drop in quality that disconnecting and reconnecting
    cleared — consistent with the codec having renegotiated downwards under the
    contention. Control traffic and the audio link share a radio. Sweep when nothing is
    playing, and keep ordinary polling modest.
    """
    if not 0 <= feature <= 0x7F:
        raise InvalidValue(f"feature out of range: {feature}")
    return Frame(VENDOR_SENNHEISER, feature, MessageType.COMMAND, PROBE_OPERATION)
