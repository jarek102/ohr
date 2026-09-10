"""The transport seam.

Interfaces only — **no implementation lives here, by design.** Everything above this
line is pure and portable; everything below it is per-platform:

============  ==========================================  ====================================
Concern       Linux                                       Windows
============  ==========================================  ====================================
RFCOMM        ``AF_BLUETOOTH`` / ``BTPROTO_RFCOMM``       WinRT ``Rfcomm`` + ``StreamSocket``
Enumeration   BlueZ over D-Bus                            WinRT ``BluetoothDevice``
============  ==========================================  ====================================

Two rules keep the seam honest:

* **Resolve services by UUID, never by channel number.** Channel numbers are
  observations that a firmware update can invalidate, and the Windows API is
  UUID-based anyway. Same call shape on both platforms, and more robust on Linux than
  the alternative.
* **Every operation takes a timeout.** A client must not be able to block
  indefinitely, because on Linux it may be holding a cross-process lease while it does
  (see :mod:`ohr.lease`).

Expressed as read/write/close over ``bytes`` rather than as a socket object, so no
implementation detail of either platform leaks upward.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

#: Service UUID advertised by the headsets this package targets.
SERVICE_UUID = "a2129ff3-081b-4c45-8afe-469d9c4842ec"


@dataclass(frozen=True, slots=True)
class DeviceInfo:
    """A discovered device.

    ``connected`` reflects the host's Bluetooth stack, not this package. Only operate
    on already-connected devices: this package never pairs, unpairs, or brings up an
    audio link.
    """

    address: str
    name: str
    connected: bool


@runtime_checkable
class Connection(Protocol):
    """An open control channel to one device."""

    def send(self, data: bytes, *, timeout: float) -> None:
        """Write ``data``. Raises on timeout rather than blocking."""
        ...

    def receive(self, *, timeout: float) -> bytes:
        """Read whatever is available.

        May return a partial frame, several frames, or a fragment. Feed the result to
        :class:`ohr.frame.FrameStream`; do not assume one call yields one frame.
        """
        ...

    def close(self) -> None:
        ...


@runtime_checkable
class Transport(Protocol):
    """Platform backend: find devices, open a control channel."""

    def list_devices(self) -> list[DeviceInfo]:
        """Devices known to the host stack. Does not scan."""
        ...

    def connect(
        self, address: str, *, service_uuid: str = SERVICE_UUID, timeout: float
    ) -> Connection:
        """Open a control channel, resolving the RFCOMM service by UUID.

        Callers should expect this to fail routinely — the vendor's phone application
        contends for the same channel, and at least one device is known to time out on
        a first attempt and succeed on a retry. Fail closed and surface it as state.
        """
        ...
