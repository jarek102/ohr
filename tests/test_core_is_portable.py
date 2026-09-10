"""Enforces the layering rule from ``docs/adr/002-layering-and-platform-seams.md``.

The core must stay importable, and fully testable, on any platform with no Bluetooth
stack present. That is not a nice-to-have: it is what lets the codec be exercised
entirely from ``vectors/``, and what keeps a second implementation in another language
a straightforward port.

The rule is easy to break by accident — one convenience import of ``socket`` for a
constant, or ``gi`` for a type — so it is checked rather than merely documented.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parents[1] / "src" / "ohr"

#: Importing any of these from core code would tie it to one platform or toolkit.
FORBIDDEN = {
    "fcntl",  # POSIX-only locking; belongs in the lease backend
    "msvcrt",  # the Windows counterpart
    "socket",  # transport backends only
    "ctypes",  # Winsock access, if it is ever used
    "subprocess",  # shelling out to bluetoothctl is a Linux backend detail
    "dbus",
    "dbus_next",
    "gi",  # GLib/GTK must never reach shared code
    "gio",
    "winrt",
    "winsdk",
    "bleak",  # BLE-only, and not this protocol — guards against a wrong turn
}


def core_modules() -> list[Path]:
    # Platform backends live in subpackages; only the flat core is covered here.
    return sorted(p for p in CORE.glob("*.py"))


def imported_roots(path: Path) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


@pytest.mark.parametrize("path", core_modules(), ids=lambda p: p.name)
def test_core_module_imports_nothing_platform_specific(path: Path) -> None:
    offending = imported_roots(path) & FORBIDDEN
    assert not offending, (
        f"{path.name} imports {sorted(offending)}, which ties the core to a platform "
        f"or toolkit. Move it behind ohr.transport or ohr.lease."
    )


def test_core_has_no_third_party_dependencies() -> None:
    """The core declares no dependencies; keep it that way."""
    pyproject = (CORE.parents[1] / "pyproject.toml").read_text()
    assert "dependencies = []" in pyproject, (
        "core dependencies are no longer empty — if that is deliberate, update this "
        "test and ADR 002 together"
    )
