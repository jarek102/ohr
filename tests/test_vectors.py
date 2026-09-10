"""Runs every fixture in ``vectors/``.

These are the conformance tests. If a change breaks one, either the change is wrong or
the vector is — and if it is the vector, fix it and say why in its ``provenance``.
Never edit an ``observed`` vector to make code pass: it records what real hardware
actually sent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ohr import Frame, MessageType, anc, battery, connections, equaliser, features
from ohr import parse_frames
from ohr.errors import InvalidLength, InvalidValue

VECTORS = Path(__file__).resolve().parents[1] / "vectors"

PAYLOAD_FILES = ("battery.json", "features.json", "anc.json", "equaliser.json",
                 "connections.json")
ALL_FILES = ("framing.json", *PAYLOAD_FILES)

ERRORS = {"invalid_length": InvalidLength, "invalid_value": InvalidValue}


def load(name: str) -> list[dict]:
    data = json.loads((VECTORS / name).read_text())
    assert data["version"] == 1, f"unexpected vector schema version in {name}"
    return data["vectors"]


def ids(vectors: list[dict]) -> list[str]:
    return [v["id"] for v in vectors]


# --- framing ----------------------------------------------------------------
#
# Frame vectors are collected from every file, not just framing.json: a write is
# pinned as complete frame bytes, and those belong beside the feature they set.

ALL = [v for name in ALL_FILES for v in load(name)]

FRAMES = [v for v in ALL if v["kind"] == "frame"]
STREAMS = [v for v in ALL if v["kind"] == "stream"]


@pytest.mark.parametrize("vec", FRAMES, ids=ids(FRAMES))
def test_frame_decodes(vec: dict) -> None:
    frame = Frame.from_bytes(bytes.fromhex(vec["bytes"]))
    assert frame.vendor == vec["vendor"]
    assert frame.feature == vec["feature"]
    assert frame.type == MessageType[vec["type"].upper()]
    assert frame.operation == vec["operation"]
    assert frame.payload.hex() == vec["payload"]


@pytest.mark.parametrize("vec", FRAMES, ids=ids(FRAMES))
def test_frame_round_trips(vec: dict) -> None:
    """Encoding the decoded fields must reproduce the original bytes exactly."""
    frame = Frame(
        vendor=vec["vendor"],
        feature=vec["feature"],
        type=MessageType[vec["type"].upper()],
        operation=vec["operation"],
        payload=bytes.fromhex(vec["payload"]),
    )
    assert frame.to_bytes().hex() == vec["bytes"]


@pytest.mark.parametrize("vec", STREAMS, ids=ids(STREAMS))
def test_stream_reassembly(vec: dict) -> None:
    buffer = b""
    got: list[Frame] = []
    for chunk in vec["chunks"]:
        buffer += bytes.fromhex(chunk)
        frames, buffer = parse_frames(buffer)
        got.extend(frames)
    assert [f.to_bytes().hex() for f in got] == vec["frames"]
    assert buffer.hex() == vec["remainder"]


# --- payloads ---------------------------------------------------------------
#
# Each entry maps a command to its decoder and a function turning the result into
# plain data, so a vector's "decoded" block can be compared directly.

def _battery_level(r: battery.BatteryLevel) -> dict:
    return {"shape": r.shape, "level": r.level, "left": r.left, "right": r.right,
            "case": r.case}


COMMANDS = {
    "battery_level": (battery.decode_level, _battery_level),
    "battery_types": (battery.decode_types, lambda r: {"first": r.first, "second": r.second}),
    "battery_charger": (battery.decode_charger, lambda r: {"first": r.first, "second": r.second}),
    "feature_list": (
        features.decode,
        lambda r: {"more": r.more,
                   "features": [{"id": e.id, "name": e.name, "version": e.version}
                                for e in r.features]},
    ),
    "anc_enabled": (anc.decode_enabled, lambda r: {"enabled": r}),
    "anc_transparency": (anc.decode_transparency, lambda r: {"enabled": r}),
    "anc_level": (anc.decode_level, lambda r: {"level": r}),
    "anc_transparency_level": (anc.decode_level, lambda r: {"level": r}),
    "anc_submodes": (
        anc.decode_submodes,
        lambda r: {"submodes": [{"id": s.id, "name": s.name, "state": s.state} for s in r]},
    ),
    "eq_mode": (equaliser.decode_mode, lambda r: {"value": r[0], "name": r[1]}),
    "eq_configuration": (
        equaliser.decode_configuration,
        lambda r: {"bands": r.bands, "gain_min_db": r.gain_min_db,
                   "gain_max_db": r.gain_max_db, "trailing": r.trailing.hex()},
    ),
    "eq_band_gain": (equaliser.decode_band_gain, lambda r: {"gain_db": r}),
    "eq_bass_boost": (equaliser.decode_bass_boost, lambda r: {"enabled": r}),
    "conn_paired_count": (connections.decode_paired_count, lambda r: {"value": r}),
    "conn_own_index": (
        lambda p: connections.decode_single_byte(p, "own index"),
        lambda r: {"value": r},
    ),
    "conn_max_connections": (
        lambda p: connections.decode_single_byte(p, "max connections"),
        lambda r: {"value": r},
    ),
    "conn_peer": (
        connections.decode_peer,
        lambda r: {"index": r.index, "device_type": r.device_type, "link": r.link,
                   "no_classic_pairing": r.no_classic_pairing, "name": r.name,
                   "valid": r.valid},
    ),
}

PAYLOADS = [v for v in ALL if v["kind"] == "payload"]


def _same(got: object, want: object, path: str = "") -> None:
    """Compare decoded data, tolerating float representation."""
    if isinstance(want, float) or isinstance(got, float):
        assert got == pytest.approx(want), path
    elif isinstance(want, dict):
        assert isinstance(got, dict) and got.keys() == want.keys(), path
        for key in want:
            _same(got[key], want[key], f"{path}.{key}")
    elif isinstance(want, list):
        assert isinstance(got, list) and len(got) == len(want), path
        for i, (g, w) in enumerate(zip(got, want, strict=True)):
            _same(g, w, f"{path}[{i}]")
    else:
        assert got == want, path


@pytest.mark.parametrize("vec", PAYLOADS, ids=ids(PAYLOADS))
def test_payload(vec: dict) -> None:
    decode, as_data = COMMANDS[vec["command"]]
    payload = bytes.fromhex(vec["payload"])

    if "error" in vec:
        with pytest.raises(ERRORS[vec["error"]]):
            decode(payload)
        return

    want = dict(vec["decoded"])
    got = as_data(decode(payload))
    # A vector need only pin the fields it cares about.
    _same({k: got[k] for k in want}, want, vec["command"])


# --- sequences --------------------------------------------------------------
#
# A user-facing setting is not always one command. These pin the whole plan: which
# frames, in which order, and the read that proves each one.


def _frames(plan) -> tuple[list[str], list[str]]:
    return (
        [step.write.to_bytes().hex() for step in plan],
        [step.read.to_bytes().hex() for step in plan],
    )


SEQUENCES = {
    "anc_mode": lambda g: _frames(
        anc.plan_mode(anc.Mode(g["target"]), anc.State(g["anc"], g["transparency"]))
    ),
    "anc_state": lambda g: _frames(
        anc.plan_state(
            anc.State(**g["target"]), anc.State(**g["current"])
        )
    ),
    "anc_level": lambda g: _frames(anc.plan_level(g["level"])),
    "anc_submode": lambda g: _frames(anc.plan_submode(g["identifier"], g["state"])),
}

SEQUENCE_VECTORS = [v for v in ALL if v["kind"] == "sequence"]


@pytest.mark.parametrize("vec", SEQUENCE_VECTORS, ids=ids(SEQUENCE_VECTORS))
def test_sequence(vec: dict) -> None:
    writes, verify = SEQUENCES[vec["sequence"]](vec["given"])
    assert writes == vec["writes"], "wrong writes, or wrong order"
    assert verify == vec["verify"], "each write must be proved by the right read"


def test_every_sequence_is_exercised() -> None:
    covered = {v["sequence"] for v in SEQUENCE_VECTORS}
    assert covered == set(SEQUENCES), (
        f"no vectors for {set(SEQUENCES) - covered}, "
        f"no planner for {covered - set(SEQUENCES)}"
    )


def test_every_command_is_exercised() -> None:
    """A decoder without a vector is unproven; a vector without a decoder cannot run."""
    covered = {v["command"] for v in PAYLOADS}
    assert covered == set(COMMANDS), (
        f"no vectors for {set(COMMANDS) - covered}, "
        f"no decoder for {covered - set(COMMANDS)}"
    )


# --- properties that hold across every vector -------------------------------


def test_every_vector_declares_provenance() -> None:
    """No fixture may exist without a stated origin.

    Guards the rule in vectors/README.md: a vector is either something a real device
    was seen to do, or something this specification requires. There is no third
    category.
    """
    for name in ALL_FILES:
        for vec in load(name):
            prov = vec.get("provenance")
            assert prov, f"{name}:{vec['id']} has no provenance"
            assert prov["kind"] in ("observed", "constructed"), (
                f"{name}:{vec['id']} has unknown provenance kind {prov['kind']!r}"
            )
            if prov["kind"] == "observed":
                assert prov.get("device") and prov.get("date"), (
                    f"{name}:{vec['id']} is observed but does not say by what, and when"
                )
            else:
                assert prov.get("rationale"), (
                    f"{name}:{vec['id']} is constructed but does not say why"
                )


def test_observed_vectors_exist_for_both_devices() -> None:
    """The two models answer differently; fixtures from only one would hide that."""
    seen = {
        vec["provenance"].get("device")
        for name in ALL_FILES
        for vec in load(name)
        if vec["provenance"]["kind"] == "observed"
    }
    assert {"accentum-wireless", "momentum-tw4"} <= seen
