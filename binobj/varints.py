"""Serializers and deserializers for variable-length integers.

"`Variable-length quantity <https://en.wikipedia.org/wiki/Variable-length_quantity>`_"
on Wikipedia.
"""

import math
import enum

import bitstring

from binobj import errors


class VarIntEncoding(enum.Enum):
    """All available encoding schemes for variable-length integers."""
    COMPACT_INDICES = 'compact'   #: Forces big endian
    GIT_VLQ = 'git'         #: Forces big endian
    LEB128 = 'leb128'       #: Forces little endian
    ULEB128 = 'uleb128'     #: Forces little endian
    VLQ = 'vlq'             #: Forces big endian
    ZIGZAG = 'zigzag'       #: Forces little endian


# TODO (dargueta): Implement the rest of the encodings.


def encode_integer_compact(field, value):   # pylint: disable=unused-argument
    """Encode an integer with the Unreal Engine Compact Indices encoding.

    :param Field field:
        The field the integer is being encoded for.
    :param int value:
        The value to encode.

    :return: The encoded integer.
    :rtype: bytes
    """
    if value == 0:
        return b'\0'

    sign_bit = 0x40 if value < 0 else 0
    n_bits = value.bit_length()
    n_bytes = int(math.ceil((n_bits + 1) / 7))

    buf = bytearray(n_bytes)

    for i in range(n_bytes - 1, 0, -1):
        buf[i] = 0x80 | (value & 0x7f)
        value >>= 7

    buf[0] = 0x80 | sign_bit | (value & 0x3f)
    buf[-1] &= 0x7f

    return bytes(buf)


def decode_integer_compact(field, stream):
    """Decode an integer with the Unreal Engine Compact Indices encoding.

    :param Field field:
        The field this integer is being decoded for.
    :param bitstring.BitStream stream:
        The bit stream to read from.

    :return: The decoded integer.
    :rtype: int
    """
    sign = None
    value = 0

    while True:
        try:
            int8 = stream.read('uint:8')
        except bitstring.ReadError:
            raise errors.UnexpectedEOFError(
                field=field, size=8, offset=stream.pos)

        if sign is None:
            # Sign hasn't been determined yet so this must be the first byte of
            # the number.
            value = int8 & 0x3f
            sign = -1 if int8 & 0x40 else 1
        else:
            value = (value << 7) | (int8 & 0x7f)

        if int8 & 0x80 == 0:
            return value * sign

#
# def encode_integer_git_vlq(field, value):
#     """Encode an integer in Git's variable-length quantity (VLQ) format.
#
#     :param Field field:
#         The field the integer is being encoded for.
#     :param int value:
#         The value to encode. Must be a non-negative integer.
#
#     :return: ``value`` encoded as a variable-length integer in Git's VLQ format.
#     :rtype: bytes
#     """
#     raise NotImplementedError
#
#
# def decode_integer_git_vlq(field, stream):
#     """pass"""
#     raise NotImplementedError
#
#
# def encode_integer_leb128(field, value):
#     """pass"""
#     raise NotImplementedError
#
#
# def decode_integer_leb128(field, data):
#     """pass"""
#     raise NotImplementedError


def encode_integer_vlq(field, value):
    """Encode an integer with the VLQ encoding.

    :param Field field:
        The field the integer is being encoded for.
    :param int value:
        The value to encode. Must be a non-negative integer.

    :return: ``value`` encoded as a variable-length integer in VLQ format.
    :rtype: bytes
    """
    if value < 0:
        raise errors.UnserializableValueError(
            reason="The VLQ integer encoding doesn't support negative numbers.",
            field=field, value=value)
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


def decode_integer_vlq(field, stream):
    """Decode a VLQ-encoded integer from the given stream.

    :param Field field:
        The field this integer is being decoded for.
    :param bitstring.BitStream stream:
        The bit stream to read from.

    :return: The decoded integer.
    :rtype: int
    """
    value = 0
    while True:
        try:
            int8 = stream.read('uint:8')
        except bitstring.ReadError:
            raise errors.UnexpectedEOFError(
                field=field, size=8, offset=stream.pos)

        value = (value << 7) | (int8 & 0x7f)
        if int8 & 0x80 == 0:
            return value


def encode_integer_zigzag(field, value):
    """Encode an integer with the Google ProtoBuff's "ZigZag" encoding.

    :param Field field:
        The field the integer is being encoded for.
    :param int value:
        The value to encode.

    :return: ``value`` encoded as a variable-length integer in "ZigZag" format.
    :rtype: bytes
    """
    if value == 0:
        return b'\0'

    n_bits = value.bit_length()
    n_bytes = int(math.ceil(n_bits / 7))

    if n_bits <= 32:
        int_size = 32
    elif n_bits <= 64:
        int_size = 64
    else:
        raise errors.UnserializableValueError(
            reason='Number is too large: %r' % value, field=field, value=value)

    encoded_value = (value << 1) ^ (value >> (int_size - 1))

    buf = bytearray(n_bytes)
    for i in range(n_bytes - 1):
        buf[i] = 0x80 | (encoded_value & 0x7f)
        encoded_value >>= 7

    buf[-1] = encoded_value & 0x7f
    return bytes(buf)


def decode_integer_zigzag(field, stream):
    """Decode a ZigZag-encoded integer from the given stream.

    :param Field field:
        The field this integer is being decoded for.
    :param bitstring.BitStream stream:
        The bit stream to read from.

    :return: The decoded integer.
    :rtype: int
    """
    value = 0
    bits_read = 0
    while True:
        try:
            int8 = stream.read('uint:8')
        except bitstring.ReadError:
            raise errors.UnexpectedEOFError(field=field, size=1,
                                            offset=stream.tell())

        value |= (int8 & 0x7f) << bits_read
        bits_read += 7
        if int8 & 0x80 == 0:
            return (value >> 1) ^ (-(value & 1))


#: A mapping of encoding enums to encode/decode functions.
INTEGER_ENCODING_MAP = {
    VarIntEncoding.COMPACT_INDICES: {
        'encode': encode_integer_compact,
        'decode': decode_integer_compact,
        'endian': 'big',
    },
    VarIntEncoding.VLQ: {
        'encode': encode_integer_vlq,
        'decode': decode_integer_vlq,
        'endian': 'big',
    },
    VarIntEncoding.ZIGZAG: {
        'encode': encode_integer_zigzag,
        'decode': decode_integer_zigzag,
        'endian': 'little',
    }
}
