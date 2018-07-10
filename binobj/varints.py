"""Serializers and deserializers for variable-length integers.

"`Variable-length quantity <https://en.wikipedia.org/wiki/Variable-length_quantity>`_"
on Wikipedia.
"""

import math
import enum

from binobj import helpers


class VarIntEncoding(enum.Enum):
    """All available encoding schemes for variable-length integers."""
    COMPACT_INDICES = 'compact'
    LEB128 = 'leb128'
    ULEB128 = 'uleb128'
    VLQ = 'vlq'
    ZIGZAG = 'zigzag'


def _read_uint8(stream):
    """Read an unsigned 8-bit integer from the given byte stream."""
    return helpers.read_int(stream, 1, signed=False)


def encode_integer_compact(value):
    """Encode an integer with the Unreal Engine Compact Indices encoding.

    :param int value:
        The value to encode.

    :return: The encoded integer.
    :rtype: bytes
    """
    if value == 0:
        return b'\0'

    if value < 0:
        sign_bit = 0x40
        value = -value
    else:
        sign_bit = 0

    n_bits = value.bit_length()
    n_bytes = 1 + int(math.ceil((n_bits - 6) / 7))

    buf = bytearray(n_bytes)

    for i in range(n_bytes - 1, 0, -1):
        buf[i] = 0x80 | (value & 0x7f)
        value >>= 7

    buf[0] = 0x80 | sign_bit | (value & 0x3f)
    buf[-1] &= 0x7f

    return bytes(buf)


def decode_integer_compact(stream):
    """Decode an integer with the Unreal Engine Compact Indices encoding.

    :param io.BufferedIOBase stream:
        The bit stream to read from.

    :return: The decoded integer.
    :rtype: int
    """
    sign = None
    value = 0

    while True:
        int8 = _read_uint8(stream)

        if sign is None:
            # Sign hasn't been determined yet so this must be the first byte of
            # the number.
            value = int8 & 0x3f
            sign = -1 if int8 & 0x40 else 1
        else:
            value = (value << 7) | (int8 & 0x7f)

        if int8 & 0x80 == 0:
            return value * sign


def encode_integer_vlq(value):
    """Encode an integer with the VLQ encoding.

    :param int value:
        The value to encode. Must be a non-negative integer.

    :return: ``value`` encoded as a variable-length integer in VLQ format.
    :rtype: bytes
    """
    if value < 0:
        raise ValueError(
            "The VLQ integer encoding doesn't support negative numbers.")
    elif value == 0:
        # Special case needed since value.bit_length() returns 0 if value is 0.
        return b'\0'

    n_bits = value.bit_length()
    n_bytes = int(math.ceil(n_bits / 7))
    buf = bytearray(n_bytes)

    for i in range(n_bytes - 1, -1, -1):
        buf[i] = 0x80 | (value & 0x7f)
        value >>= 7

    buf[-1] &= 0x7f
    return bytes(buf)


def decode_integer_vlq(stream):
    """Decode a VLQ-encoded integer from the given stream.

    :param io.BufferedIOBase stream:
        The stream to read from.

    :return: The decoded integer.
    :rtype: int
    """
    value = 0
    while True:
        int8 = _read_uint8(stream)

        value = (value << 7) | (int8 & 0x7f)
        if int8 & 0x80 == 0:
            return value


def encode_integer_zigzag(value):
    """Encode an integer with the Google Protobuf's "ZigZag" encoding.

    :param int value:
        The value to encode.

    :return: ``value`` encoded as a variable-length integer in "ZigZag" format.
    :rtype: bytes
    """
    if value == 0:
        return b'\0'

    n_bits = value.bit_length()
    n_bytes = int(math.ceil(n_bits / 7))

    if n_bits <= 31:
        int_size = 32
    elif n_bits <= 63:
        int_size = 64
    else:
        raise OverflowError('Number is too large: %r' % value)

    encoded_value = (value << 1) ^ (value >> (int_size - 1))

    buf = bytearray(n_bytes)
    for i in range(n_bytes - 1):
        buf[i] = 0x80 | (encoded_value & 0x7f)
        encoded_value >>= 7

    buf[-1] = encoded_value & 0x7f
    return bytes(buf)


def decode_integer_zigzag(stream):
    """Decode a ZigZag-encoded integer from the given stream.

    :param io.BufferedIOBase stream:
        The stream to read from.

    :return: The decoded integer.
    :rtype: int
    """
    value = 0
    bits_read = 0
    while True:
        int8 = _read_uint8(stream)

        value |= (int8 & 0x7f) << bits_read
        bits_read += 7
        if int8 & 0x80 == 0:
            return (value >> 1) ^ (-(value & 1))


def encode_integer_uleb128(value):
    """Encode an integer with unsigned LEB128 encoding.

    :param int value:
        The value to encode.

    :return: ``value`` encoded as a variable-length integer in ULEB128 format.
    :rtype: bytes
    """
    if value < 0:
        raise ValueError(
            "The ULEB128 integer encoding doesn't support negative numbers.")
    elif value == 0:
        return b'\0'

    output = bytearray()

    while value > 0:
        continue_bit = 0x80 if value > 127 else 0
        output.append(continue_bit | (value & 0x7f))
        value >>= 7

    return bytes(output)


def decode_integer_uleb128(stream):
    """Decode an unsigned LEB128-encoded integer from the given stream.

    :param io.BufferedIOBase stream:
        The stream to read from.

    :return: The decoded integer.
    :rtype: int
    """
    value = 0
    bits_read = 0

    while True:
        int8 = _read_uint8(stream)
        value |= (int8 & 0x7f) << bits_read
        bits_read += 7

        if not int8 & 0x80:
            return value


def encode_integer_leb128(value):
    """Encode an integer with signed LEB128 encoding.

    :param int value:
        The value to encode.

    :return: ``value`` encoded as a variable-length integer in LEB128 format.
    :rtype: bytes
    """
    if value == 0:
        return b'\0'

    # Calculate the number of bits in the integer and round up to the nearest
    # multiple of 7. We need to add 1 bit because bit_length() only returns the
    # number of bits required to encode the magnitude, but not the sign.

    n_bits = value.bit_length() + 1
    if n_bits % 7:
        n_bits += 7 - (n_bits % 7)

    # Bit operations force a negative integer to its unsigned twos-complement
    # representation, e.g. -127 & 0xff = 0x80, -10 & 0xfff = 0xff6, etc. We use
    # this to sign-extend the number *and* make it unsigned. Once it's unsigned,
    # we can use ULEB128.
    mask = (1 << n_bits) - 1
    value &= mask

    output = bytearray(n_bits // 7)

    for i in range(n_bits // 7):
        output[i] = 0x80 | (value & 0x7f)
        value >>= 7

    # Last byte shouldn't have the high bit set.
    output[-1] &= 0x7f
    return bytes(output)


def decode_integer_leb128(stream):
    """Decode a signed LEB128-encoded integer from the given stream.

    :param io.BufferedIOBase stream:
        The stream to read from.

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
        'encode': encode_integer_compact,
        'decode': decode_integer_compact,
        'endian': 'big',
        'signed': True,
    },
    VarIntEncoding.LEB128: {
        'encode': encode_integer_leb128,
        'decode': decode_integer_leb128,
        'endian': 'little',
        'signed': True,
    },
    VarIntEncoding.ULEB128: {
        'encode': encode_integer_uleb128,
        'decode': decode_integer_uleb128,
        'endian': 'little',
        'signed': False,
    },
    VarIntEncoding.VLQ: {
        'encode': encode_integer_vlq,
        'decode': decode_integer_vlq,
        'endian': 'big',
        'signed': False,
    },
    VarIntEncoding.ZIGZAG: {
        'encode': encode_integer_zigzag,
        'decode': decode_integer_zigzag,
        'endian': 'little',
        'signed': True,
    },
}
