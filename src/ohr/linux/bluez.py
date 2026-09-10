"""Device enumeration through BlueZ.

Read-only. This package never pairs, unpairs, connects an audio link or otherwise
changes the host's Bluetooth state — it reports what BlueZ already knows and operates
only on devices that are already connected.
"""

from __future__ import annotations

from ..errors import DeviceNotFound, TransportError
from ..transport import DeviceInfo

_BLUEZ = "org.bluez"
_DEVICE_IFACE = "org.bluez.Device1"
_OBJECT_MANAGER = "org.freedesktop.DBus.ObjectManager"


def _managed_objects() -> dict:
    try:
        import dbus  # noqa: PLC0415 — optional, and only on this platform
    except ImportError as exc:  # pragma: no cover - depends on host packages
        raise TransportError(
            "dbus-python is required for device enumeration; install the 'linux' extra"
        ) from exc
    try:
        bus = dbus.SystemBus()
        manager = dbus.Interface(bus.get_object(_BLUEZ, "/"), _OBJECT_MANAGER)
        return manager.GetManagedObjects()
    except Exception as exc:  # pragma: no cover - depends on a running bluetoothd
        raise TransportError(f"could not talk to BlueZ: {exc}") from exc


def list_devices(*, service_uuid: str | None = None) -> list[DeviceInfo]:
    """Every device BlueZ knows about.

    With ``service_uuid``, only devices advertising it are returned — which is the
    cheap way to tell a supported headset from any other paired peripheral, and does
    not touch the device.
    """
    devices: list[DeviceInfo] = []
    for interfaces in _managed_objects().values():
        properties = interfaces.get(_DEVICE_IFACE)
        if not properties:
            continue
        uuids = {str(u).lower() for u in properties.get("UUIDs", [])}
        if service_uuid and service_uuid.lower() not in uuids:
            continue
        devices.append(
            DeviceInfo(
                address=str(properties.get("Address", "")),
                name=str(properties.get("Alias") or properties.get("Name") or ""),
                connected=bool(properties.get("Connected", False)),
            )
        )
    return sorted(devices, key=lambda d: d.address)


def find_device(address: str, *, service_uuid: str | None = None) -> DeviceInfo:
    """Look up one device by address.

    Raises :class:`ohr.errors.DeviceNotFound` if BlueZ does not know it, or if
    ``service_uuid`` is given and the device does not advertise it.
    """
    wanted = address.upper()
    for device in list_devices(service_uuid=service_uuid):
        if device.address.upper() == wanted:
            return device
    raise DeviceNotFound(
        f"{address} is not known to BlueZ"
        + (" as a device advertising this service" if service_uuid else "")
    )
