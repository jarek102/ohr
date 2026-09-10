"""RFCOMM transport for Linux."""

from __future__ import annotations

import socket

from ..errors import ChannelUnresolved, DeviceNotFound, TransportError
from ..transport import SERVICE_UUID, Connection, DeviceInfo
from . import bluez, channels, sdp


class RfcommConnection:
    """One open control channel.

    Satisfies :class:`ohr.transport.Connection` structurally; it does not inherit,
    because the protocol is the contract and inheritance would only risk silently
    picking up an unimplemented stub.
    """

    __slots__ = ("_sock", "address", "channel")

    def __init__(self, sock: socket.socket, address: str, channel: int) -> None:
        self._sock = sock
        self.address = address
        self.channel = channel

    def send(self, data: bytes, *, timeout: float) -> None:
        self._sock.settimeout(timeout)
        self._sock.sendall(data)

    def receive(self, *, timeout: float) -> bytes:
        self._sock.settimeout(max(timeout, 0.01))
        chunk = self._sock.recv(4096)
        if not chunk:
            raise TransportError("the device closed the control channel")
        return chunk

    def close(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass

    def __enter__(self) -> RfcommConnection:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class LinuxTransport:
    """Finds devices through BlueZ and opens RFCOMM control channels."""

    def list_devices(self, *, service_uuid: str | None = SERVICE_UUID) -> list[DeviceInfo]:
        return bluez.list_devices(service_uuid=service_uuid)

    def connect(
        self,
        address: str,
        *,
        service_uuid: str = SERVICE_UUID,
        timeout: float = 5.0,
        channel: int | None = None,
        retries: int = 1,
    ) -> RfcommConnection:
        """Open a control channel to an already-connected device.

        The channel is resolved in this order: the one supplied, then one remembered
        from a previous success, then service discovery. If none of those produces a
        channel, :class:`ohr.errors.ChannelUnresolved` is raised rather than guessing —
        the library ships no channel numbers.

        ``retries`` exists because a first attempt failing is not evidence of anything.
        At least one known model reproducibly times out once and answers immediately
        afterwards.
        """
        device = bluez.find_device(address, service_uuid=service_uuid)
        if not device.connected:
            raise DeviceNotFound(
                f"{address} is not connected; this package does not bring up links"
            )

        resolved = channel or channels.get(address) or sdp.resolve_rfcomm_channel(
            address, service_uuid
        )
        if not resolved:
            raise ChannelUnresolved(
                f"no channel for {address}: service discovery returned nothing and none "
                f"is cached. Pass one explicitly and it will be remembered."
            )

        last: OSError | None = None
        for _ in range(retries + 1):
            sock = socket.socket(
                socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM
            )
            try:
                sock.settimeout(timeout)
                sock.connect((address, resolved))
            except OSError as exc:
                sock.close()
                last = exc
                continue
            channels.remember(address, resolved)
            return RfcommConnection(sock, address, resolved)

        raise TransportError(
            f"could not open channel {resolved} on {address}: {last}"
        ) from last
