"""Noise control: ANC, transparency, submodes and level.

Two features, not one. ANC is feature 13; transparency (letting outside sound through)
is feature 12, with its own commands. The user-facing choice between *ANC*,
*Transparency* and *Off* is a combination of the two, not a single setting — which is
why writing a mode is a sequence rather than one command, and why a half-applied
sequence is a real state rather than a theoretical one.

The two flags are **not mutually exclusive on the wire**: both have been observed
enabled at once. Nothing here treats them as a three-valued enum.

Pure: no I/O. Writes are described here and executed by :mod:`ohr.control`, which
verifies each one by read-back.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from .control import Step
from .errors import InvalidLength, InvalidValue
from .frame import Frame, MessageType, VENDOR_SENNHEISER

FEATURE_TRANSPARENT_HEARING = 12
FEATURE_ANC = 13

OP_SET_SUBMODE = 0
OP_SUBMODES = 1
OP_SET_LEVEL = 2
OP_LEVEL = 3
OP_SET_ENABLED = 4
OP_ENABLED = 5

#: Levels travel as a percentage byte, matching the read encoding.
LEVEL_STEPS = 100

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
    """The level, read against whatever the flags currently are. Empty payload.

    With transparency off this is the ANC level. With transparency on it reads full
    scale on both models — and that is *not* the transparency level, which has its own
    read and was 0.75 on one of them at the time. Read this alongside the flags or it
    means nothing.
    """
    return Frame(VENDOR_SENNHEISER, FEATURE_ANC, MessageType.COMMAND, OP_LEVEL)


def request_transparency_level() -> Frame:
    """The stored transparency level, whether or not transparency is on. Empty payload.

    Feature 12 keeps its own level, and this read is unaffected by the mode — which is
    what makes it useful: it is the only one of the two that means the same thing every
    time it is called.
    """
    return Frame(
        VENDOR_SENNHEISER, FEATURE_TRANSPARENT_HEARING, MessageType.COMMAND, OP_LEVEL
    )


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


# --- writes -----------------------------------------------------------------
#
# Setters reply with an empty acknowledgement carrying no state. Send these through
# ohr.control.apply rather than directly, so each one is proved by a read.


def request_set_enabled(on: bool) -> Frame:
    """Turn ANC on or off. Payload is one flag byte.

    **Turning ANC on also clears the transparency flag.** Writing ``True`` to a device
    that already has ANC on still dropped transparency, so the side effect belongs to
    the write and not to any change of value. Turning ANC *off* leaves transparency
    alone; the coupling runs one way only.

    **It is audible, in both directions, on both models** — the one setter here that is,
    as configured. Devices carry a tone-and-prompts setting the owner can change, so no
    client can know whether a write will be heard. Assume it may be: send this only when
    the flag is actually changing, or when its side effect on transparency is the point.
    """
    return Frame(
        VENDOR_SENNHEISER,
        FEATURE_ANC,
        MessageType.COMMAND,
        OP_SET_ENABLED,
        bytes([1 if on else 0]),
    )


def request_set_transparency(on: bool) -> Frame:
    """Turn transparency on or off. Payload is one flag byte.

    A different feature from ANC, so this neither implies nor cancels the other.

    Audibility differs by model: silent on the earbuds, while the over-ear model plays
    a tone — and a *different* one from the ANC tone, so that device distinguishes the
    two modes by ear. Treat a redundant write as something the wearer may hear.
    """
    return Frame(
        VENDOR_SENNHEISER,
        FEATURE_TRANSPARENT_HEARING,
        MessageType.COMMAND,
        OP_SET_ENABLED,
        bytes([1 if on else 0]),
    )


def request_set_level(level: float) -> Frame:
    """Set the level, as a fraction of full scale. Payload is one percentage byte.

    **This clears the transparency flag and leaves ANC alone.** Writing the level a
    device already reported still clears it, so the side effect belongs to the write
    rather than to any change of value. A caller must re-read the flags afterwards, not
    just the level.

    The consequence depends on where the device started: from transparency with ANC off
    it lands on off, and from both-on it lands on ANC. Neither is what someone adjusting
    a level expects, which is why this is a mode change wearing a parameter's clothes.

    Audibility differs by model: silent on the earbuds, while the over-ear model plays
    a tone for 0 and 100 but not for values between them. No difference in the sound of
    the cancelling was reported between those endpoints, so what this changes is not
    obvious by ear.

    Rejects anything outside 0.0–1.0 rather than clamping: a caller asking for 1.5 has
    a bug, and silently writing full scale would hide it.
    """
    if not 0.0 <= level <= 1.0:
        raise InvalidValue(f"level must be between 0.0 and 1.0, got {level}")
    return Frame(
        VENDOR_SENNHEISER,
        FEATURE_ANC,
        MessageType.COMMAND,
        OP_SET_LEVEL,
        bytes([round(level * LEVEL_STEPS)]),
    )


def request_set_submode(identifier: int, state: int) -> Frame:
    """Set one submode. Payload is ``(identifier, state)``.

    **Audible on the earbuds**, where every submode change plays a tone; not reported on
    the over-ear model. Send it only when something is actually changing.

    The accepted range of ``state`` differs per submode and is not advertised by any
    read, so it is not validated here beyond fitting in a byte. Verify by read-back —
    there is no read for a single submode, so :func:`plan_submode` re-reads them all.
    """
    if not 0 <= identifier <= 0xFF:
        raise InvalidValue(f"submode identifier out of range: {identifier}")
    if not 0 <= state <= 0xFF:
        raise InvalidValue(f"submode state out of range: {state}")
    return Frame(
        VENDOR_SENNHEISER,
        FEATURE_ANC,
        MessageType.COMMAND,
        OP_SET_SUBMODE,
        bytes([identifier, state]),
    )


# --- the three user-facing modes --------------------------------------------


class Mode(enum.Enum):
    """What a person means by the three-way choice in a noise-control UI.

    This is a **presentation over two independent flags**, not a field on the device.
    Availability is a per-product decision that no read exposes — in particular a
    device may not offer *off* — so a mode is attempted and verified, never assumed
    supported.
    """

    ANC = "anc"
    TRANSPARENCY = "transparency"
    OFF = "off"


@dataclass(frozen=True, slots=True)
class State:
    """The two flags, as last read.

    ``transparency`` is ``None`` when the device does not implement feature 12 or the
    read did not answer. That is not the same as off, and the difference changes the
    plan: a state that is unknown is not turned off on the way past.
    """

    anc: bool
    transparency: bool | None = None

    @property
    def mode(self) -> Mode | None:
        """Which mode this state presents as, or ``None`` if it presents as neither.

        The precedence — transparency first — is a **rule this library defines**, not
        something the device reports, because both flags can be set at once and the
        pair has no ordering of its own. It matches what selecting *Transparency*
        leaves behind, which is the state a user is most likely looking at.
        """
        if self.transparency:
            return Mode.TRANSPARENCY
        if self.anc:
            return Mode.ANC
        if self.transparency is None:
            # ANC is off and transparency is unknown, which is not enough to call it
            # off. Say nothing rather than report a mode that was never read.
            return None
        return Mode.OFF


def _enabled_step(on: bool) -> Step:
    return Step(
        label=f"anc {'on' if on else 'off'}",
        write=request_set_enabled(on),
        read=request_enabled(),
        decode=decode_enabled,
        expect=on,
    )


def _transparency_step(on: bool) -> Step:
    return Step(
        label=f"transparency {'on' if on else 'off'}",
        write=request_set_transparency(on),
        read=request_transparency(),
        decode=decode_transparency,
        expect=on,
    )


def plan_mode(target: Mode, current: State) -> tuple[Step, ...]:
    """The writes that select ``target``, given what the device currently reports.

    Order is not arbitrary. Each sequence turns something **off before turning
    something on**, so that if it stops halfway the device is quieter than intended
    rather than louder — the safer failure for something worn over the ears.

    Selecting *Transparency* does not clear ANC. That mirrors what the vendor
    application does, and is consistent with both flags having been observed set at
    once; clearing it here would be this library inventing behaviour.

    The plan depends on ``current``, so it must be built from a fresh read. Feeding it
    a stale state produces a sequence that verifies correctly and still leaves the
    wrong mode selected.

    **The ANC write is audible**, on both models and in both directions, so a flag
    already in the wanted position is left alone rather than written for tidiness — a
    redundant enable is a beep in someone's ears. The transparency write is audible on
    one model too, and is skipped on the same terms; there is no reason to send either.

    That makes an empty plan a normal answer, meaning *already there*, rather than a
    failure to produce one.
    """
    if target is Mode.ANC:
        steps = []
        if current.transparency:
            steps.append(_transparency_step(False))
        if not current.anc:
            steps.append(_enabled_step(True))
        return tuple(steps)

    if target is Mode.TRANSPARENCY:
        return (_transparency_step(True),)

    steps = [_enabled_step(False)]
    if current.transparency is not None:
        # Unknown is not off: without a reading there is nothing to verify against.
        steps.append(_transparency_step(False))
    return tuple(steps)


def plan_state(target: State, current: State) -> tuple[Step, ...]:
    """The writes that reproduce ``target`` exactly, flag by flag.

    Distinct from :func:`plan_mode`, and the distinction is what makes an undo
    trustworthy: a mode is a *presentation* of two flags, and more than one flag
    combination presents as the same mode. Restoring by mode can therefore leave a
    device in a state it was not in — selecting *Transparency* again does not put ANC
    back the way it was found.

    Flags already correct produce no write — with one exception, which is the whole
    reason this function is not a two-line loop. **Enabling ANC clears transparency**
    (see :func:`request_set_enabled`), so a transparency flag that is already correct
    stops being correct the moment an ANC-on write goes out ahead of it. It is
    rewritten in that case rather than skipped.

    Skipping it instead produces the worst available outcome: a plan that verifies
    every write it makes and still leaves the device somewhere else. On the over-ear
    model that rewrite is a second audible tone, which is a real cost and still the
    lesser one: the alternative is leaving the device in a state nobody asked for.

    Everything that must go off goes off first, matching :func:`plan_mode`, and ANC is
    set before transparency so the coupling runs before the flag it would disturb.
    """
    off: list[Step] = []
    on: list[Step] = []

    if target.anc != current.anc:
        (on if target.anc else off).append(_enabled_step(target.anc))
    enabling_anc = any(step.expect for step in on)

    if target.transparency is False and current.transparency:
        off.append(_transparency_step(False))
    elif target.transparency and (not current.transparency or enabling_anc):
        on.append(_transparency_step(True))

    return (*off, *on)


def plan_level(level: float) -> tuple[Step, ...]:
    """The write that sets the level, with its read-back.

    The read reports hundredths, so a request is compared against the value the device
    will be able to express rather than against the float as asked.

    Verifies the level only. The same write moves the transparency flag (see
    :func:`request_set_level`), and that is deliberately left to the caller: a step
    verifies the setting it asked for, and a plan that quietly restored a flag it had
    not been asked about would be doing something other than what it says.
    """
    return (
        Step(
            label=f"level {level:.2f}",
            write=request_set_level(level),
            read=request_level(),
            decode=decode_level,
            expect=round(level * LEVEL_STEPS) / LEVEL_STEPS,
        ),
    )


def plan_submode(identifier: int, state: int) -> tuple[Step, ...]:
    """The write that sets one submode, verified against the full submode list.

    There is no read for a single submode: verification re-reads them all and picks out
    the one that was written, which also catches a device that moves another submode in
    response.
    """

    def just_this_one(payload: bytes) -> int | None:
        return next(
            (s.state for s in decode_submodes(payload) if s.id == identifier), None
        )

    return (
        Step(
            label=f"submode {SUBMODES.get(identifier, identifier)} = {state}",
            write=request_set_submode(identifier, state),
            read=request_submodes(),
            decode=just_this_one,
            expect=state,
        ),
    )
