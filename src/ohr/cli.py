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


def _probe_plan() -> list[tuple[str, object, object]]:
    """Every read this library knows, as (label, request, decoder)."""
    from . import anc, connections, equaliser

    return [
        ("battery.level", battery.request_level(), battery.decode_level),
        ("battery.types", battery.request_types(), battery.decode_types),
        ("battery.charger", battery.request_charger(), battery.decode_charger),
        ("anc.enabled", anc.request_enabled(), anc.decode_enabled),
        ("anc.transparency", anc.request_transparency(), anc.decode_transparency),
        ("anc.submodes", anc.request_submodes(), anc.decode_submodes),
        ("anc.level", anc.request_level(), anc.decode_level),
        ("eq.mode", equaliser.request_mode(), equaliser.decode_mode),
        ("eq.configuration", equaliser.request_configuration(), equaliser.decode_configuration),
        ("eq.bass_boost", equaliser.request_bass_boost(), equaliser.decode_bass_boost),
        ("conn.paired_count", connections.request_paired_count(), connections.decode_paired_count),
        ("conn.own_index", connections.request_own_index(),
         lambda p: connections.decode_single_byte(p, "own index")),
        ("conn.max", connections.request_max_connections(),
         lambda p: connections.decode_single_byte(p, "max connections")),
    ]


def _cmd_probe(args: argparse.Namespace) -> int:
    """Issue every known read and report raw bytes alongside the decode.

    Read-only. Nothing here mutates device state.
    """
    import json

    from . import connections, equaliser
    from .frame import MessageType
    from .linux import FlockLease, LinuxTransport

    results: list[dict] = []

    def run(label: str, request, decode) -> None:
        entry: dict = {"label": label, "tx": request.to_bytes().hex()}
        try:
            reply = session.request(request, timeout=args.timeout)
        except ProtocolError as exc:
            entry["error"] = f"{type(exc).__name__}: {exc}"
            results.append(entry)
            return
        entry["rx"] = reply.to_bytes().hex()
        entry["payload"] = reply.payload.hex()
        entry["type"] = reply.type.name.lower()
        if reply.type is MessageType.ERROR:
            entry["error"] = "device returned an error frame"
        else:
            try:
                entry["decoded"] = repr(decode(reply.payload))
            except ProtocolError as exc:
                entry["error"] = f"decode failed: {type(exc).__name__}: {exc}"
        results.append(entry)

    with FlockLease().acquire(args.address, timeout=args.lease_timeout):
        with LinuxTransport().connect(
            args.address, timeout=args.timeout, channel=args.channel
        ) as connection:
            session = Session(connection)
            for label, request, decode in _probe_plan():
                run(label, request, decode)

            # Bands and peers are enumerated from what the device just reported.
            config = next(
                (r for r in results if r["label"] == "eq.configuration" and "decoded" in r),
                None,
            )
            if config:
                bands = equaliser.decode_configuration(bytes.fromhex(config["payload"])).bands
                for band in range(min(bands, args.max_enumerate)):
                    run(
                        f"eq.band[{band}]",
                        equaliser.request_band_gain(band),
                        equaliser.decode_band_gain,
                    )
            for index in range(args.max_enumerate):
                before = len(results)
                run(f"conn.peer[{index}]", connections.request_peer(index),
                    connections.decode_peer)
                entry = results[before]
                if "error" in entry or "valid=False" in entry.get("decoded", ""):
                    break

    if args.json:
        print(json.dumps({"address": args.address, "reads": results}, indent=2))
    else:
        for entry in results:
            outcome = entry.get("decoded") or entry.get("error", "")
            print(f"{entry['label']:22} {entry.get('payload', '—'):<24} {outcome}")
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

    probe = sub.add_parser(
        "probe", help="issue every known read and show the raw bytes (read-only)"
    )
    probe.add_argument("address")
    probe.add_argument("--channel", type=int)
    probe.add_argument("--timeout", type=float, default=5.0)
    probe.add_argument("--lease-timeout", type=float, default=2.0)
    probe.add_argument(
        "--max-enumerate",
        type=int,
        default=8,
        help="upper bound when walking bands and peer slots",
    )
    probe.add_argument("--json", action="store_true")
    probe.set_defaults(func=_cmd_probe)

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
