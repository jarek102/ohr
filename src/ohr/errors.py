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

    Expected, not exceptional: another controller may be a peer that cannot be
    coordinated with. Callers should render this as a state, not a crash.
    """


class TransportError(ProtocolError):
    """A transport backend could not do what was asked."""


class DeviceNotFound(TransportError):
    """No such device is known to the host, or it is not connected.

    This package never pairs and never brings up a link; it operates only on devices
    the host has already connected.
    """


class ChannelUnresolved(TransportError):
    """The service could not be located on the device.

    Raised when service discovery yields nothing and no channel is cached or supplied.
    Not fatal: a caller that knows the channel may pass it explicitly, and it is
    remembered afterwards.
    """


class ReplyTimeout(TransportError):
    """No matching reply arrived in time.

    A timeout is not evidence that a command is unsupported — at least one known device
    fails a first request and answers a retry.
    """
