"""Various helper functions for stream I/O."""

import sys

from binobj import errors


def read_int(stream, n_bytes, signed=True, endian=None):
    """Read an integer from the given byte stream.

    :param io.BufferedIOBase stream:
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

    :param io.BufferedIOBase stream:
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


def iter_bytes(stream, max_bytes=0):
    """Wrap a stream in an iterator that yields individual bytes, not lines.

    :param stream:
        A stream opened in binary mode.
    :param int max_bytes:
        The maximum number of bytes to read.
    """
    n_read = 0

    while not max_bytes or n_read < max_bytes:
        this_byte = stream.read(1)
        if this_byte == b'':
            return
        yield this_byte
        n_read += 1
