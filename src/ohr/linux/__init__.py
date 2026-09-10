"""Linux platform backend.

Everything in this package is Linux-specific, and nothing above it is. The core imports
none of this — see
[ADR 002](../../../docs/adr/002-layering-and-platform-seams.md), enforced by
``tests/test_core_is_portable.py``.

Three seams live here: the RFCOMM socket (:mod:`ohr.linux.rfcomm`), device enumeration
through BlueZ (:mod:`ohr.linux.bluez`), and the cross-process lease
(:mod:`ohr.linux.lease`). Service discovery (:mod:`ohr.linux.sdp`) supports the first,
and :mod:`ohr.linux.channels` remembers what discovery could not tell us.
"""

from __future__ import annotations

from .lease import FlockLease
from .rfcomm import LinuxTransport, RfcommConnection

__all__ = ["FlockLease", "LinuxTransport", "RfcommConnection"]
