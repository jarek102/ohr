"""Command line interface — the first consumer of the library.

``devices``, ``status`` and ``probe`` are read-only. ``anc`` writes, and every write it
makes is verified by a read-back; ``--dry-run`` shows the exact frames without sending
them, and ``--restore`` puts the previous setting back afterwards.
"""

from __future__ import annotations

import argparse
import sys
from typing import NamedTuple

from . import anc, battery, control, features
from .errors import ChannelUnresolved, DeviceBusy, ProtocolError
from .frame import MessageType
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
    from . import anc, audio, connections, device, equaliser

    return [
        ("device.version", device.request_version(), device.decode_versions),
        ("device.version_wide", device.request_version_wide(), device.decode_version_wide),
        ("device.product_name", device.request_product_name(), device.decode_product_name),
        ("device.on_head_detect", device.request_on_head_detection(),
         device.decode_on_head_detection),
        ("audio.codec", audio.request_codec(), audio.decode_codec),
        ("audio.prompts", audio.request_prompts(), audio.decode_prompts),
        ("audio.prompt_language", audio.request_prompt_language(),
         audio.decode_prompt_language),
        ("device.local_name", device.request_local_name(), device.decode_local_name),
        ("device.aptx_96k", device.request_aptx_96k_support(),
         device.decode_aptx_96k_support),
        ("device.aptx_lossless", device.request_aptx_lossless_support(),
         device.decode_aptx_lossless_support),
        ("power.eco_mode", battery.request_eco_mode(), battery.decode_eco_mode),
        ("power.battery_protection", battery.request_battery_protection(),
         battery.decode_battery_protection),
        ("anc.auto_pause", anc.request_auto_pause(), anc.decode_auto_pause),
        ("battery.level", battery.request_level(), battery.decode_level),
        ("battery.types", battery.request_types(), battery.decode_types),
        ("battery.charger", battery.request_charger(), battery.decode_charger),
        ("anc.enabled", anc.request_enabled(), anc.decode_enabled),
        ("anc.transparency", anc.request_transparency(), anc.decode_transparency),
        ("anc.submodes", anc.request_submodes(), anc.decode_submodes),
        ("anc.level", anc.request_level(), anc.decode_level),
        ("anc.transparency_level", anc.request_transparency_level(), anc.decode_level),
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


class Snapshot(NamedTuple):
    """Noise control as one reading. Recorded before a change, so it can be put back."""

    state: anc.State
    level: float | None
    submodes: tuple
    transparency_level: float | None = None


def _read_noise_control(
    session: Session, timeout: float
) -> tuple[anc.State, float | None, tuple, float | None]:
    """Everything the noise-control screen shows, as one snapshot.

    Transparency is read into ``None`` rather than ``False`` when the device declines
    it: a setting that was never read is not a setting that is off, and the difference
    changes what a mode change is allowed to write.
    """

    def read(request, decode):
        reply = session.request(request, timeout=timeout)
        if reply.type is MessageType.ERROR:
            return None
        try:
            return decode(reply.payload)
        except ProtocolError:
            return None

    enabled = read(anc.request_enabled(), anc.decode_enabled)
    if enabled is None:
        raise ProtocolError("device did not report whether ANC is on")
    return (
        anc.State(
            anc=enabled,
            transparency=read(anc.request_transparency(), anc.decode_transparency),
        ),
        read(anc.request_level(), anc.decode_level),
        read(anc.request_submodes(), anc.decode_submodes) or (),
        read(anc.request_transparency_level(), anc.decode_level),
    )


def _show(
    state: anc.State,
    level: float | None,
    submodes: tuple,
    transparency_level: float | None = None,
) -> None:
    mode = state.mode
    print(f"  mode         {mode.value if mode else 'unknown'}")
    print(f"  anc          {'on' if state.anc else 'off'}")
    transparency = "unavailable" if state.transparency is None else (
        "on" if state.transparency else "off"
    )
    print(f"  transparency {transparency}")
    if level is not None:
        # Whichever path is active, so it is labelled by what it actually is.
        print(f"  active level {level * 100:.0f}%")
    if transparency_level is not None:
        print(f"  transp level {transparency_level * 100:.0f}%")
    for submode in submodes:
        print(f"  submode      {submode.name or submode.id} = {submode.state}")


def _plan_for(args: argparse.Namespace, state: anc.State) -> tuple:
    if args.mode:
        return anc.plan_mode(anc.Mode(args.mode), state)
    if args.level is not None:
        return anc.plan_level(args.level)
    identifier, _, value = args.submode.partition("=")
    ids = {name: number for number, name in anc.SUBMODES.items()}
    if identifier not in ids:
        raise SystemExit(f"unknown submode {identifier!r}; known: {', '.join(sorted(ids))}")
    return anc.plan_submode(ids[identifier], int(value))


def _cmd_anc(args: argparse.Namespace) -> int:
    from .linux import FlockLease, LinuxTransport

    changing = args.mode or args.level is not None or args.submode

    with FlockLease().acquire(args.address, timeout=args.lease_timeout):
        with LinuxTransport().connect(
            args.address, timeout=args.timeout, channel=args.channel
        ) as connection:
            session = Session(connection)
            before = Snapshot(*_read_noise_control(session, args.timeout))

            print(f"{args.address}  channel {connection.channel}")
            _show(*before)
            if not changing:
                return 0

            plan = _plan_for(args, before.state)

            if args.dry_run:
                print(f"\nwould send {len(plan)} write(s):")
                for step in plan:
                    print(f"  {step.label:22} {step.write.to_bytes().hex()}")
                    print(f"  {'verify by':22} {step.read.to_bytes().hex()}")
                return 0

            if not plan:
                # Not a failure to build one: the device is already there, and writing
                # a flag that is already set would beep at whoever is wearing it.
                print("\nalready in that state — nothing to write")
                return 0

            print(f"\napplying ({len(plan)} write(s), each verified by read-back):")
            result = control.apply(session, plan, timeout=args.timeout)
            for outcome in result.outcomes:
                print(f"  {'ok  ' if outcome.ok else 'FAIL'} {outcome.describe()}")

            print("\nnow:")
            _show(*_read_noise_control(session, args.timeout))

            if args.restore:
                if args.level is not None and before.state.transparency:
                    # The setter writes the ANC level and drops transparency on the way
                    # past. Restoring the flag brings back the transparency level, which
                    # was never touched — but the ANC level it overwrote is gone, and
                    # there is no read that distinguishes the two to compare against.
                    print(
                        "\nnote: this wrote the ANC level and left transparency; "
                        "restoring the flag does not put the previous ANC level back"
                    )
                if not _restore(session, args.timeout, before):
                    return 4

            return 0 if result.complete else 4


def _reconcile(target: Snapshot, current: Snapshot) -> tuple:
    """The writes that turn ``current`` back into ``target``.

    Whole-snapshot, not just the field that was changed, because **a write here does
    not necessarily stay in its lane**: setting the level was observed clearing the
    transparency flag. An undo that replays only what it deliberately changed would
    leave the device somewhere it had never been, and report success doing it.

    The level is reconciled only once the flags already match. The level read reports
    whichever path is active, so comparing across different flag settings compares two
    different quantities — and writing the answer would store a transparency level as
    an ANC one.
    """
    steps = list(anc.plan_state(target.state, current.state))
    if steps:
        return tuple(steps)

    if target.level is not None and current.level != target.level:
        steps.extend(anc.plan_level(target.level))
    for want in target.submodes:
        have = next((s.state for s in current.submodes if s.id == want.id), None)
        if have is not None and have != want.state:
            steps.extend(anc.plan_submode(want.id, want.state))
    return tuple(steps)


def _restore(session: Session, timeout: float, target: Snapshot, rounds: int = 4) -> bool:
    """Put the device back, re-reading between rounds until nothing differs.

    Rounds rather than a single plan, because settings here are coupled: restoring one
    can move another. Convergence is checked by reading, never assumed from a plan
    having been sent.
    """
    for attempt in range(1, rounds + 1):
        plan = _reconcile(target, Snapshot(*_read_noise_control(session, timeout)))
        if not plan:
            print("\nrestored" if attempt > 1 else "\nnothing to restore: as found")
            return True
        print(f"\nrestoring, round {attempt} ({len(plan)} write(s)):")
        result = control.apply(session, plan, timeout=timeout)
        for outcome in result.outcomes:
            print(f"  {'ok  ' if outcome.ok else 'FAIL'} {outcome.describe()}")
        if not result.complete:
            print("the device was NOT returned to its previous state")
            return False

    if _reconcile(target, Snapshot(*_read_noise_control(session, timeout))):
        print(f"still differs after {rounds} rounds; the device was NOT restored")
        return False
    print("\nrestored")
    return True


def _cmd_eq(args: argparse.Namespace) -> int:
    from . import equaliser
    from .linux import FlockLease, LinuxTransport

    with FlockLease().acquire(args.address, timeout=args.lease_timeout):
        with LinuxTransport().connect(
            args.address, timeout=args.timeout, channel=args.channel
        ) as connection:
            session = Session(connection)
            config = equaliser.decode_configuration(
                session.request(equaliser.request_configuration(), timeout=args.timeout).payload
            )
            gains = {
                band: equaliser.decode_band_gain(
                    session.request(equaliser.request_band_gain(band),
                                    timeout=args.timeout).payload
                )
                for band in range(config.bands)
            }
            boost = equaliser.decode_bass_boost(
                session.request(equaliser.request_bass_boost(), timeout=args.timeout).payload
            )
            mode = equaliser.decode_mode(
                session.request(equaliser.request_mode(), timeout=args.timeout).payload
            )

            print(f"{args.address}  channel {connection.channel}")
            print(f"  mode         {mode[1] or mode[0]}")
            print(f"  range        {config.gain_min_db:+.1f} to {config.gain_max_db:+.1f} dB")
            for band, gain in gains.items():
                print(f"  band {band}       {gain:+.1f} dB")
            print(f"  bass boost   {'on' if boost else 'off'}")

            plan: tuple = ()
            if args.band is not None:
                if args.gain is None:
                    print("--band needs --gain", file=sys.stderr)
                    return 1
                try:
                    plan = equaliser.plan_band_gain(args.band, args.gain, config)
                except ProtocolError as exc:
                    print(f"{exc}", file=sys.stderr)
                    return 1
            elif args.bass_boost:
                plan = equaliser.plan_bass_boost(args.bass_boost == "on")

            if not plan:
                return 0

            if args.dry_run:
                print(f"\nwould send {len(plan)} write(s):")
                for step in plan:
                    print(f"  {step.label:22} {step.write.to_bytes().hex()}")
                    print(f"  {'verify by':22} {step.read.to_bytes().hex()}")
                return 0

            print(f"\napplying ({len(plan)} write(s), each verified by read-back):")
            result = control.apply(session, plan, timeout=args.timeout)
            for outcome in result.outcomes:
                print(f"  {'ok  ' if outcome.ok else 'FAIL'} {outcome.describe()}")

            if args.restore:
                back = (
                    equaliser.plan_band_gain(args.band, gains[args.band], config)
                    if args.band is not None
                    else equaliser.plan_bass_boost(boost)
                )
                print(f"\nrestoring:")
                for outcome in control.apply(session, back, timeout=args.timeout).outcomes:
                    print(f"  {'ok  ' if outcome.ok else 'FAIL'} {outcome.describe()}")

            return 0 if result.complete else 4


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

    eq = sub.add_parser(
        "eq",
        help="show the equaliser, and set a band",
        description=(
            "With no option, reads the equaliser. --band sets one band and verifies it "
            "by reading it back. A preset is one write per band, so partial application "
            "is real — use --restore to put the previous curve back."
        ),
    )
    eq.add_argument("address")
    eq.add_argument("--band", type=int, metavar="INDEX")
    eq.add_argument("--gain", type=float, metavar="DB",
                    help="gain in decibels, clamped to the device's reported range")
    eq.add_argument("--bass-boost", choices=["on", "off"])
    eq.add_argument("--dry-run", action="store_true")
    eq.add_argument("--restore", action="store_true",
                    help="put the previous value back afterwards, verifying that too")
    eq.add_argument("--channel", type=int)
    eq.add_argument("--timeout", type=float, default=5.0)
    eq.add_argument("--lease-timeout", type=float, default=2.0)
    eq.set_defaults(func=_cmd_eq)

    noise = sub.add_parser(
        "anc",
        help="show noise control, and change it",
        description=(
            "With no option, reads and shows the current state. With one, writes it "
            "and verifies by reading back — a mode is up to two writes, so a change "
            "can be partially applied, and this reports which step stopped."
        ),
    )
    noise.add_argument("address")
    change = noise.add_mutually_exclusive_group()
    change.add_argument(
        "--mode",
        choices=[m.value for m in anc.Mode],
        help="the three-way choice, applied as a sequence of writes",
    )
    change.add_argument(
        "--level", type=float, metavar="0.0-1.0", help="noise-control level"
    )
    change.add_argument(
        "--submode",
        metavar="NAME=VALUE",
        help=f"one submode, e.g. adaptive=1; known: {', '.join(sorted(anc.SUBMODES.values()))}",
    )
    noise.add_argument(
        "--dry-run",
        action="store_true",
        help="print the frames that would be sent, and send nothing",
    )
    noise.add_argument(
        "--restore",
        action="store_true",
        help="put the previous setting back afterwards, verifying that too",
    )
    noise.add_argument("--channel", type=int)
    noise.add_argument("--timeout", type=float, default=5.0)
    noise.add_argument("--lease-timeout", type=float, default=2.0)
    noise.set_defaults(func=_cmd_anc)

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
