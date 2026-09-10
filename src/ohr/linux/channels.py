"""Remembering which RFCOMM channel served a device.

Service discovery does not answer on every device (see :mod:`ohr.linux.sdp`), so a
channel that worked once is worth keeping. This is a cache, not configuration: deleting
it costs one rediscovery, and a stale entry is corrected the next time a connection
succeeds on a different channel.

Nothing here is a default. The library ships no channel numbers — an unknown device is
an unknown device until discovery answers or a caller supplies one.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def _cache_path() -> Path:
    root = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(root) / "ohr" / "channels.json"


def _load() -> dict[str, int]:
    path = _cache_path()
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return {str(k).upper(): int(v) for k, v in data.items() if isinstance(v, int)}


def get(address: str) -> int | None:
    """The channel last known to work for ``address``, if any."""
    return _load().get(address.upper())


def remember(address: str, channel: int) -> None:
    """Record a channel that worked. Best effort — a failure here is not an error."""
    cache = _load()
    if cache.get(address.upper()) == channel:
        return
    cache[address.upper()] = channel
    path = _cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n")
    except OSError:
        pass


def forget(address: str) -> None:
    """Drop a remembered channel, so the next connection rediscovers."""
    cache = _load()
    if cache.pop(address.upper(), None) is None:
        return
    try:
        _cache_path().write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n")
    except OSError:
        pass
