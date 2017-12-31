"""Various helper functions for stream I/O."""

import sys

from binobj import errors


def merge_dicts(target, source):
    """An implementation of :meth:`dict.update` that doesn't overwrite existing
    keys.

    :param dict target:
        The dictionary to set keys in. This is modified in place, so you should
        make a copy if you don't want to modify the original.
    :param dict source:
        The dictionary to get new keys from.

    :return: ``target``
    :rtype: dict
    """
    for key, value in source.items():
        target.setdefault(key, value)
    return target


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
        :data:`sys.byteorder`.

    :return: The integer loaded from the byte stream.
    :rtype: int

    :raise UnexpectedEOFError:
        The end of the stream was hit before ``n_bytes`` bytes were read.
    """
    if not endian:
        endian = sys.byteorder

    offset = stream.tell()
    data = stream.read(n_bytes)
    if len(data) < n_bytes:
        raise errors.UnexpectedEOFError(field=None, size=n_bytes, offset=offset)

    return int.from_bytes(data, endian, signed=signed)


def write_int(stream, value, n_bytes, signed=True, endian=None):
    """Write an integer to a stream.

    :param io.BytesIO stream:
        The stream to write the integer to.
    :param int value:
        The integer to dump into the stream.
    :param int n_bytes:
        The number of bytes the integer should take up. Exactly this many bytes
        will be written into the stream, so ensure that there's enough bits to
        represent ``value``.
    :param bool signed:
        If ``True``, write this integer in twos-complement format. Otherwise,
        write it as an unsigned integer. A negative ``value`` will trigger an
        :class:`OverflowError` if this is ``False``.
    :param str endian:
        The endianness to use when writing the integer, either ``big`` or
        ``little``. If not given, will default to the system's native byte order
        as given by :data:`sys.byteorder`.

    :raise OverflowError:
        ``value`` can't be represented only by ``n_bytes`` bytes. The number is
        too big, or it's negative and ``signed`` is ``False``.
    """
    if not endian:
        endian = sys.byteorder

    stream.write(value.to_bytes(n_bytes, endian, signed=signed))


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
