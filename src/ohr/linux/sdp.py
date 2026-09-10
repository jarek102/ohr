"""Service discovery through libbluetooth.

Resolves an RFCOMM channel from a service UUID, which is what
[ADR 002](../../../docs/adr/002-layering-and-platform-seams.md) asks for: channel
numbers are observations that firmware can invalidate, so they should be discovered
rather than assumed.

**This does not work against every device.** Some headsets answer an SDP search with an
empty record set — verified 2026-09-09 against two models, where searches for the
vendor service, the Serial Port profile and even the public browse group all returned
success with zero records, while the same devices happily advertised those UUIDs
through BlueZ. :func:`resolve_rfcomm_channel` returns ``None`` in that case rather than
raising, and the caller falls back to a cached or supplied channel.
"""

from __future__ import annotations

import ctypes
import uuid as _uuid

_SDP_RETRY_IF_BUSY = 0x01
_SDP_ATTR_REQ_RANGE = 1
_RFCOMM_UUID = 0x0003
_ALL_ATTRIBUTES = 0x0000FFFF
_ANY_ADAPTER = b"00:00:00:00:00:00"

# uuid_t is `uint8_t type` plus a union holding at most 16 bytes; 32 is generous.
_UUID_T_SIZE = 32


class _BdAddr(ctypes.Structure):
    _fields_ = [("b", ctypes.c_uint8 * 6)]


class _SdpList(ctypes.Structure):
    pass


_SdpList._fields_ = [("next", ctypes.POINTER(_SdpList)), ("data", ctypes.c_void_p)]


def _load() -> ctypes.CDLL | None:
    for name in ("libbluetooth.so.3", "libbluetooth.so"):
        try:
            lib = ctypes.CDLL(name, use_errno=True)
        except OSError:
            continue
        lib.str2ba.argtypes = [ctypes.c_char_p, ctypes.POINTER(_BdAddr)]
        lib.sdp_connect.argtypes = [
            ctypes.POINTER(_BdAddr),
            ctypes.POINTER(_BdAddr),
            ctypes.c_uint32,
        ]
        lib.sdp_connect.restype = ctypes.c_void_p
        lib.sdp_uuid128_create.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        lib.sdp_uuid128_create.restype = ctypes.c_void_p
        lib.sdp_list_append.argtypes = [ctypes.POINTER(_SdpList), ctypes.c_void_p]
        lib.sdp_list_append.restype = ctypes.POINTER(_SdpList)
        lib.sdp_service_search_attr_req.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_SdpList),
            ctypes.c_int,
            ctypes.POINTER(_SdpList),
            ctypes.POINTER(ctypes.POINTER(_SdpList)),
        ]
        lib.sdp_service_search_attr_req.restype = ctypes.c_int
        lib.sdp_get_access_protos.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.POINTER(_SdpList)),
        ]
        lib.sdp_get_access_protos.restype = ctypes.c_int
        lib.sdp_get_proto_port.argtypes = [ctypes.POINTER(_SdpList), ctypes.c_int]
        lib.sdp_get_proto_port.restype = ctypes.c_int
        lib.sdp_close.argtypes = [ctypes.c_void_p]
        return lib
    return None


_LIB = _load()

#: Whether service discovery is available at all on this host.
AVAILABLE = _LIB is not None


def resolve_rfcomm_channel(address: str, service_uuid: str) -> int | None:
    """Return the RFCOMM channel serving ``service_uuid``, or ``None``.

    ``None`` means *not discoverable*, which is a routine outcome — see the module
    docstring. It never means the service is absent; check the advertised UUID list for
    that.
    """
    if _LIB is None:
        return None

    src, dst = _BdAddr(), _BdAddr()
    _LIB.str2ba(_ANY_ADAPTER, ctypes.byref(src))
    _LIB.str2ba(address.encode(), ctypes.byref(dst))

    session = _LIB.sdp_connect(ctypes.byref(src), ctypes.byref(dst), _SDP_RETRY_IF_BUSY)
    if not session:
        return None
    try:
        target = (ctypes.c_uint8 * _UUID_T_SIZE)()
        _LIB.sdp_uuid128_create(ctypes.byref(target), _uuid.UUID(service_uuid).bytes)
        search = _LIB.sdp_list_append(None, ctypes.byref(target))

        attributes = ctypes.c_uint32(_ALL_ATTRIBUTES)
        attribute_list = _LIB.sdp_list_append(None, ctypes.byref(attributes))

        response = ctypes.POINTER(_SdpList)()
        if _LIB.sdp_service_search_attr_req(
            session, search, _SDP_ATTR_REQ_RANGE, attribute_list, ctypes.byref(response)
        ) != 0:
            return None

        node = response
        while node:
            protocols = ctypes.POINTER(_SdpList)()
            if _LIB.sdp_get_access_protos(node.contents.data, ctypes.byref(protocols)) == 0:
                channel = _LIB.sdp_get_proto_port(protocols, _RFCOMM_UUID)
                if channel > 0:
                    return int(channel)
            node = node.contents.next
        return None
    finally:
        _LIB.sdp_close(session)
