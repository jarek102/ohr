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

from ohr import Frame, MessageType, battery, features, parse_frames
from ohr.errors import InvalidLength

VECTORS = Path(__file__).resolve().parents[1] / "vectors"

ERRORS = {"invalid_length": InvalidLength}


def load(name: str) -> list[dict]:
    data = json.loads((VECTORS / name).read_text())
    assert data["version"] == 1, f"unexpected vector schema version in {name}"
    return data["vectors"]


def ids(vectors: list[dict]) -> list[str]:
    return [v["id"] for v in vectors]


# --- framing ----------------------------------------------------------------

FRAMES = [v for v in load("framing.json") if v["kind"] == "frame"]
STREAMS = [v for v in load("framing.json") if v["kind"] == "stream"]


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

BATTERY = load("battery.json")
FEATURES = load("features.json")


def _check_error(vec: dict, decode, payload: bytes) -> bool:
    if "error" not in vec:
        return False
    with pytest.raises(ERRORS[vec["error"]]):
        decode(payload)
    return True


@pytest.mark.parametrize("vec", BATTERY, ids=ids(BATTERY))
def test_battery(vec: dict) -> None:
    payload = bytes.fromhex(vec["payload"])

    if vec["command"] == "battery_level":
        if _check_error(vec, battery.decode_level, payload):
            return
        got = battery.decode_level(payload)
        want = vec["decoded"]
        assert got.shape == want["shape"]
        for field in ("level", "left", "right", "case"):
            expected = want.get(field)
            actual = getattr(got, field)
            if expected is None:
                assert actual is None, f"{field} should be unavailable"
            else:
                assert actual == pytest.approx(expected), field

    elif vec["command"] == "battery_types":
        if _check_error(vec, battery.decode_types, payload):
            return
        got_types = battery.decode_types(payload)
        assert got_types.first == vec["decoded"]["first"]
        assert got_types.second == vec["decoded"]["second"]

    else:  # pragma: no cover
        pytest.fail(f"unknown command {vec['command']}")


@pytest.mark.parametrize("vec", FEATURES, ids=ids(FEATURES))
def test_feature_list(vec: dict) -> None:
    payload = bytes.fromhex(vec["payload"])
    if _check_error(vec, features.decode, payload):
        return
    got = features.decode(payload)
    want = vec["decoded"]
    assert got.more == want["more"]
    assert [
        {"id": e.id, "name": e.name, "version": e.version} for e in got.features
    ] == want["features"]


# --- properties that hold across every vector -------------------------------


def test_every_vector_declares_provenance() -> None:
    """No fixture may exist without a stated origin.

    Guards the rule in vectors/README.md: a vector is either something a real device
    was seen to do, or something this specification requires. There is no third
    category.
    """
    for name in ("framing.json", "battery.json", "features.json"):
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
        for name in ("framing.json", "battery.json", "features.json")
        for vec in load(name)
        if vec["provenance"]["kind"] == "observed"
    }
    assert {"accentum-wireless", "momentum-tw4"} <= seen
