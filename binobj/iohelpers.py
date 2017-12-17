"""Various helper functions for stream I/O."""

import sys

from binobj import errors


def read_int(stream, n_bytes, signed=True, endian=None):
    """Read an integer from the given byte stream.

    :param io.BytesIO stream:
        The stream to read from.
    :param int n_bytes:
        The number of bytes to read for this integer.
    :param bool signed:
        If ``True``, interpret this integer as a twos-complement signed integer.
        Otherwise, interpret it as an unsigned integer.
    :param str endian:
        The endianness of the integer, either ``big`` or ``little``. If not
        given, will default to the system's native byte order as given by
        `sys.byteorder`.
    """
    if not endian:
        endian = sys.byteorder

    offset = stream.tell()
    data = stream.read(n_bytes)
    if len(data) < n_bytes:
        raise errors.UnexpectedEOFError(field=None, size=n_bytes, offset=offset)

    return int.from_bytes(data, endian, signed=signed)


def read_int8(stream):
    """Load a signed 8-bit integer from the given byte stream."""
    return read_int(stream, 1, signed=True)


def read_uint8(stream):
    """Load an unsigned 8-bit integer from the given byte stream."""
    return read_int(stream, 1, signed=False)


def read_int16(stream, endian=None):
    """Load a signed 16-bit integer from the given byte stream."""
    return read_int(stream, 2, endian=endian, signed=True)


def read_uint16(stream, endian=None):
    """Load an unsigned 16-bit integer from the given byte stream."""
    return read_int(stream, 2, endian=endian, signed=False)


def read_int32(stream, endian=None):
    """Load a signed 32-bit integer from the given byte stream."""
    return read_int(stream, 4, endian=endian, signed=True)


def read_uint32(stream, endian=None):
    """Load an unsigned 32-bit integer from the given byte stream."""
    return read_int(stream, 4, endian=endian, signed=False)


def read_int64(stream, endian=None):
    """Load a signed 64-bit integer from the given byte stream."""
    return read_int(stream, 8, endian=endian, signed=True)


def read_uint64(stream, endian=None):
    """Load an unsigned 64-bit integer from the given byte stream."""
    return read_int(stream, 8, endian=endian, signed=False)
