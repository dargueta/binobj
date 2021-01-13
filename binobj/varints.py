"""Serializers and deserializers for `variable-length integers`_.

.. _variable-length integers: https://en.wikipedia.org/wiki/Variable-length_quantity
"""

import enum
import math
import typing
from typing import BinaryIO

from binobj import helpers


if typing.TYPE_CHECKING:  # pragma: no cover
    from typing import Optional


class VarIntEncoding(enum.Enum):
    """All available encoding schemes for variable-length integers."""

    COMPACT_INDICES = "compact"
    """Signed big-endian integer in `modified VLQ`_ format.

    .. _modified VLQ: https://en.wikipedia.org/wiki/Variable-length_quantity#Sign_bit
    """

    LEB128 = "leb128"
    """Signed little-endian integer in `LEB128`_ format.

    .. _LEB128: https://en.wikipedia.org/wiki/LEB128
    """

    ULEB128 = "uleb128"
    """Unsigned little-endian integer in `LEB128`_ format.

    .. _LEB128: https://en.wikipedia.org/wiki/LEB128
    """

    VLQ = "vlq"
    """Unsigned big-endian integer in `VLQ`_ format.

    .. _VLQ: https://en.wikipedia.org/wiki/Variable-length_quantity#General_structure
    """


def _read_uint8(stream: BinaryIO) -> int:
    """Read an unsigned 8-bit integer from the given byte stream."""
    return helpers.read_int(stream, 1, signed=False)


def encode_integer_compact(value: int) -> bytes:
    """Encode an integer with signed VLQ encoding.

    :param int value: The value to encode.

    :return: The encoded integer.
    :rtype: bytes
    """
    if value == 0:
        return b"\0"

    if value < 0:
        sign_bit = 0x40
        value = -value
    else:
        sign_bit = 0

    n_bits = value.bit_length()
    n_bytes = 1 + int(math.ceil((n_bits - 6) / 7))

    buf = bytearray(n_bytes)

    for i in range(n_bytes - 1, 0, -1):
        buf[i] = 0x80 | (value & 0x7F)
        value >>= 7

    buf[0] = 0x80 | sign_bit | (value & 0x3F)
    buf[-1] &= 0x7F

    return bytes(buf)


def decode_integer_compact(stream: BinaryIO) -> int:
    """Decode an integer with signed VLQ encoding.

    :param BinaryIO stream: The stream to read from.

    :return: The decoded integer.
    :rtype: int
    """
    sign = None  # type: Optional[int]
    value = 0

    while True:
        int8 = _read_uint8(stream)

        if sign is None:
            # Sign hasn't been determined yet so this must be the first byte of
            # the number.
            value = int8 & 0x3F
            sign = -1 if int8 & 0x40 else 1
        else:
            value = (value << 7) | (int8 & 0x7F)

        if int8 & 0x80 == 0:
            return value * sign


def encode_integer_vlq(value: int) -> bytes:
    """Encode an integer with the unsigned VLQ encoding.

    :param int value:
        The value to encode. Must be a non-negative integer.

    :return: ``value`` encoded as a variable-length integer in VLQ format.
    :rtype: bytes
    """
    if value < 0:
        raise ValueError("The VLQ integer encoding doesn't support negative numbers.")
    if value == 0:
        # Special case needed since value.bit_length() returns 0 if value is 0.
        return b"\0"

    n_bits = value.bit_length()
    n_bytes = int(math.ceil(n_bits / 7))
    buf = bytearray(n_bytes)

    for i in range(n_bytes - 1, -1, -1):
        buf[i] = 0x80 | (value & 0x7F)
        value >>= 7

    buf[-1] &= 0x7F
    return bytes(buf)


def decode_integer_vlq(stream: BinaryIO) -> int:
    """Decode an unsigned VLQ-encoded integer from the given stream.

    :param BinaryIO stream: The stream to read from.

    :return: The decoded integer.
    :rtype: int
    """
    value = 0
    while True:
        int8 = _read_uint8(stream)

        value = (value << 7) | (int8 & 0x7F)
        if int8 & 0x80 == 0:
            return value


def encode_integer_uleb128(value: int) -> bytes:
    """Encode an integer with unsigned LEB128 encoding.

    :param int value: The value to encode.

    :return: ``value`` encoded as a variable-length integer in ULEB128 format.
    :rtype: bytes
    """
    if value < 0:
        raise ValueError(
            "The ULEB128 integer encoding doesn't support negative numbers."
        )
    if value == 0:
        return b"\0"

    output = bytearray()

    while value > 0:
        continue_bit = 0x80 if value > 127 else 0
        output.append(continue_bit | (value & 0x7F))
        value >>= 7

    return bytes(output)


def decode_integer_uleb128(stream: BinaryIO) -> int:
    """Decode an unsigned LEB128-encoded integer from the given stream.

    :param BinaryIO stream: The stream to read from.

    :return: The decoded integer.
    :rtype: int
    """
    value = 0
    bits_read = 0

    while True:
        int8 = _read_uint8(stream)
        value |= (int8 & 0x7F) << bits_read
        bits_read += 7

        if not int8 & 0x80:
            return value


def encode_integer_leb128(value: int) -> bytes:
    """Encode an integer with signed LEB128 encoding.

    :param int value: The value to encode.

    :return: ``value`` encoded as a variable-length integer in LEB128 format.
    :rtype: bytes
    """
    if value == 0:
        return b"\0"

    # Calculate the number of bits in the integer and round up to the nearest
    # multiple of 7. We need to add 1 bit because bit_length() only returns the
    # number of bits required to encode the magnitude, but not the sign.

    n_bits = value.bit_length() + 1
    if n_bits % 7:
        n_bits += 7 - (n_bits % 7)

    # Bit operations force a negative integer to its unsigned two's-complement
    # representation, e.g. -127 & 0xff = 0x80, -10 & 0xfff = 0xff6, etc. We use
    # this to sign-extend the number *and* make it unsigned. Once it's unsigned,
    # we can use ULEB128.
    mask = (1 << n_bits) - 1
    value &= mask

    output = bytearray(n_bits // 7)

    for i in range(n_bits // 7):
        output[i] = 0x80 | (value & 0x7F)
        value >>= 7

    # Last byte shouldn't have the high bit set.
    output[-1] &= 0x7F
    return bytes(output)


def decode_integer_leb128(stream: BinaryIO) -> int:
    """Decode a signed LEB128-encoded integer from the given stream.

    :param BinaryIO stream: The stream to read from.

    :return: The decoded integer.
    :rtype: int
    """
    starting_offset = stream.tell()
    value = decode_integer_uleb128(stream)
    if value == 0:
        return 0

    n_bytes_read = stream.tell() - starting_offset
    n_bits_read = n_bytes_read * 7
    n_value_bits = value.bit_length()

    if n_bits_read > n_value_bits:
        return value

    # `value` is negative.
    return -((1 << n_bits_read) - value)


#: A mapping of encoding enums to encode/decode functions.
INTEGER_ENCODING_MAP = {
    VarIntEncoding.COMPACT_INDICES: {
        "encode": encode_integer_compact,
        "decode": decode_integer_compact,
        "endian": "big",
        "signed": True,
    },
    VarIntEncoding.LEB128: {
        "encode": encode_integer_leb128,
        "decode": decode_integer_leb128,
        "endian": "little",
        "signed": True,
    },
    VarIntEncoding.ULEB128: {
        "encode": encode_integer_uleb128,
        "decode": decode_integer_uleb128,
        "endian": "little",
        "signed": False,
    },
    VarIntEncoding.VLQ: {
        "encode": encode_integer_vlq,
        "decode": decode_integer_vlq,
        "endian": "big",
        "signed": False,
    },
}
