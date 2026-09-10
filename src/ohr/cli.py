"""Command line interface — the first consumer of the library.

Read-only. Nothing here writes to a device.
"""

from __future__ import annotations

import argparse
import sys

from . import battery, features
from .errors import ChannelUnresolved, DeviceBusy, ProtocolError
from .session import Session
from .transport import SERVICE_UUID


def _percent(value: float | None) -> str:
    return "unavailable" if value is None else f"{value * 100:.0f}%"


def _cmd_devices(args: argparse.Namespace) -> int:
    from .linux import LinuxTransport

    devices = LinuxTransport().list_devices(
        service_uuid=None if args.all else SERVICE_UUID
    )
    if not devices:
        print("no matching devices known to BlueZ")
        return 1
    for device in devices:
        state = "connected" if device.connected else "disconnected"
        print(f"{device.address}  {state:12}  {device.name}")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    from .linux import FlockLease, LinuxTransport

    transport = LinuxTransport()
    with FlockLease().acquire(args.address, timeout=args.lease_timeout):
        with transport.connect(
            args.address, timeout=args.timeout, channel=args.channel
        ) as connection:
            session = Session(connection)
            print(f"{args.address}  channel {connection.channel}")

            level = session.request(battery.request_level(), timeout=args.timeout)
            reading = battery.decode_level(level.payload)
            if reading.shape == "scalar":
                print(f"  battery      {_percent(reading.level)}")
            else:
                print(
                    f"  battery      left {_percent(reading.left)}  "
                    f"right {_percent(reading.right)}  case {_percent(reading.case)}"
                )

            types = session.request(battery.request_types(), timeout=args.timeout)
            decoded = battery.decode_types(types.payload)
            print(f"  cell type    {decoded.first} / {decoded.second}")

            listing = features.decode(
                session.request(features.request(), timeout=args.timeout).payload
            )
            while listing.more:
                # Only when the device says so; a spurious continuation is a bug.
                nxt = features.decode(
                    session.request(
                        features.request_continuation(), timeout=args.timeout
                    ).payload
                )
                listing = features.merge(listing, nxt)

            print(f"  features     {len(listing.features)}")
            for entry in sorted(listing.features, key=lambda e: e.id):
                name = entry.name or f"unnamed ({entry.id})"
                print(f"    {entry.id:3}  {name:22} v{entry.version}")

            if session.pending_events:
                print(f"  unsolicited  {session.pending_events} frame(s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ohr", description="Read state from a Sennheiser Bluetooth headset."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    devices = sub.add_parser("devices", help="list devices advertising the service")
    devices.add_argument(
        "--all", action="store_true", help="do not filter by service UUID"
    )
    devices.set_defaults(func=_cmd_devices)

    status = sub.add_parser("status", help="read state from one device")
    status.add_argument("address", help="Bluetooth address, as shown by 'ohr devices'")
    status.add_argument(
        "--channel",
        type=int,
        help="RFCOMM channel, when discovery cannot find it; remembered afterwards",
    )
    status.add_argument("--timeout", type=float, default=5.0)
    status.add_argument("--lease-timeout", type=float, default=2.0)
    status.set_defaults(func=_cmd_status)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except DeviceBusy as exc:
        print(f"busy: {exc}", file=sys.stderr)
        return 2
    except ChannelUnresolved as exc:
        print(f"{exc}", file=sys.stderr)
        print("hint: pass --channel once and it will be cached", file=sys.stderr)
        return 3
    except ProtocolError as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
