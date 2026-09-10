"""Validates every vector file against ``vectors/schema.json``.

The schema is part of the published artifact, not a convenience: an implementation in
another language can validate the fixtures before consuming them. So it has to stay
correct, which means something must check it.

Skipped when ``jsonschema`` is absent, so the core suite still runs with no
dependencies at all (see ADR 002).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema", reason="install the 'dev' extra")

VECTORS = Path(__file__).resolve().parents[1] / "vectors"
FILES = sorted(p for p in VECTORS.glob("*.json") if p.name != "schema.json")


@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads((VECTORS / "schema.json").read_text())


def test_schema_is_itself_valid(schema: dict) -> None:
    jsonschema.Draft202012Validator.check_schema(schema)


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_vector_file_matches_schema(path: Path, schema: dict) -> None:
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(json.loads(path.read_text())), key=str)
    assert not errors, "\n".join(
        f"{'/'.join(str(p) for p in e.absolute_path)}: {e.message}" for e in errors
    )


def test_every_vector_file_is_covered() -> None:
    """A new vector file must be picked up, not silently ignored."""
    assert {p.name for p in FILES} == {
        "framing.json", "battery.json", "features.json",
        "anc.json", "equaliser.json", "connections.json",
    }, (
        "vector files changed — add the new one to the runner in test_vectors.py too, "
        "or it will validate but never execute"
    )
