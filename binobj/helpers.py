"""Various helper functions for stream I/O."""

from __future__ import annotations

import sys
from typing import BinaryIO
from typing import TYPE_CHECKING

from binobj import errors


if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Iterator

    from binobj.typedefs import EndianString


def read_int(
    stream: BinaryIO,
    n_bytes: int,
    signed: bool = True,
    endian: EndianString | None = None,
) -> int:
    """Read an integer from the given byte stream.

    :param BinaryIO stream:
        The stream to read from.
    :param int n_bytes:
        The number of bytes to read for this integer.
    :param bool signed:
        If ``True``, interpret this integer as a two's-complement signed integer.
        Otherwise, interpret it as an unsigned integer.
    :param str endian:
        The endianness of the integer, either ``big`` or ``little``. If not given, will
        default to the system's native byte order as given by :data:`sys.byteorder`.

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


def write_int(
    stream: BinaryIO,
    value: int,
    n_bytes: int,
    signed: bool = True,
    endian: EndianString | None = None,
) -> None:
    """Write an integer to a stream.

    Arguments:
        stream (BinaryIO):
            The stream to write the integer to.
        value (int):
            The integer to dump into the stream.
        n_bytes (int):
            The number of bytes the integer should take up. Exactly this many bytes will
            be written into the stream, so ensure that there's enough bits to represent
            ``value``.
        signed (bool):
            If ``True``, write this integer in two's-complement format. Otherwise, write
            it as an unsigned integer. A negative ``value`` will trigger an
            :class:`OverflowError` if this is ``False``.
        endian (str):
            The endianness to use when writing the integer, either "big" or "little". If
            not given, will default to the system's native byte order as given by
            :data:`sys.byteorder`.

    Raises:
        OverflowError:
            ``value`` can't be represented only by ``n_bytes`` bytes. The number is too
            big, or it's negative and ``signed`` is ``False``.
    """
    if not endian:
        endian = sys.byteorder
    stream.write(value.to_bytes(n_bytes, endian, signed=signed))


def iter_bytes(stream: BinaryIO, max_bytes: int | None = None) -> Iterator[bytes]:
    """Wrap a stream in an iterator that yields individual bytes, not lines.

    Arguments:
        stream (BinaryIO):
            A stream opened in binary mode.
        max_bytes (int):
            The maximum number of bytes to read.

    Yields:
        Individual bytes from the stream.

    .. versionadded:: 0.2.1
    """
    n_read = 0

    while max_bytes is None or n_read < max_bytes:
        this_byte = stream.read(1)
        if this_byte == b"":
            return
        yield this_byte
        n_read += 1


def peek_bytes(stream: BinaryIO, count: int, short_read_okay: bool = True) -> bytes:
    """Read the next ``count`` bytes in the stream without moving the stream pointer.

    Returns:
        bytes: The data read.

    Raises:
        EOFError: Fewer than `count` bytes were left in the input.

    .. versionadded:: 0.9.0
    """
    here = stream.tell()
    try:
        data = stream.read(count)
    finally:
        stream.seek(here)

    if not short_read_okay and len(data) < count:
        raise EOFError(
            f"Short read: expected {count} bytes in stream, read {len(data)}."
        )
    return data
