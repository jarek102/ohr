"""Advisory-lock lease for Linux.

Implements the first backend described in
[ADR 003](../../../docs/adr/003-control-channel-ownership.md): a per-device lock file
held with ``flock``.

``flock`` releases automatically when the holding process dies, so there is no stale
lock to clean up and no pidfile to get wrong. It does **not** release for a process that
is merely wedged, which is why every transport operation takes a timeout — a lease must
never be held across an unbounded wait.

This mediates local processes only. Another controller elsewhere is a peer that cannot
be coordinated with, so callers must handle failure regardless.
"""

from __future__ import annotations

import errno
import fcntl
import os
import time
from pathlib import Path

from ..errors import DeviceBusy


def _lock_dir() -> Path:
    root = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"  # noqa: S108 - fallback only
    return Path(root) / "ohr"


class FlockLease:
    """An exclusive local claim on one device's control channel.

    Per device address, not global — driving two headsets at once is fine::

        with FlockLease().acquire(address, timeout=2.0):
            ...
    """

    __slots__ = ("_fd", "_path", "address")

    def __init__(self) -> None:
        self._fd: int | None = None
        self._path: Path | None = None
        self.address: str | None = None

    def acquire(self, address: str, *, timeout: float = 2.0) -> FlockLease:
        """Claim the channel, or raise :class:`ohr.errors.DeviceBusy`.

        Polls rather than blocking, so a caller always regains control within
        ``timeout`` and can present contention as a state.
        """
        directory = _lock_dir()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{address.upper().replace(':', '')}.lock"
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)

        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EAGAIN):
                    os.close(fd)
                    raise
                if time.monotonic() >= deadline:
                    os.close(fd)
                    raise DeviceBusy(
                        f"another process holds the control channel for {address}"
                    ) from exc
                time.sleep(0.05)
            else:
                break

        self._fd, self._path, self.address = fd, path, address
        return self

    def release(self) -> None:
        if self._fd is None:
            return
        try:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
        finally:
            os.close(self._fd)
            self._fd = self._path = self.address = None

    @property
    def held(self) -> bool:
        return self._fd is not None

    def __enter__(self) -> FlockLease:
        return self

    def __exit__(self, *exc: object) -> None:
        self.release()
