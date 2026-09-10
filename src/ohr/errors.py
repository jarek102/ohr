"""Exception types.

Kept deliberately small. Decoders raise; they never return a sentinel that a caller
might mistake for data.
"""

from __future__ import annotations


class ProtocolError(Exception):
    """Base for every error raised by this package."""


class InvalidLength(ProtocolError):
    """A payload or frame was not a length this command accepts.

    Raised rather than truncating or zero-filling. A short battery payload is not a
    battery reading of zero.
    """


class InvalidValue(ProtocolError):
    """A field held a value outside the set this command defines."""


class DeviceBusy(ProtocolError):
    """Another client holds the control channel for this device.

    Expected, not exceptional: the vendor's own phone application is a peer that
    cannot be coordinated with. Callers should render this as a state, not a crash.
    """
