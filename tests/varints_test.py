"""Tests for the variable-length integers."""

import bitstring
import pytest

from binobj import errors
from binobj import varints


@pytest.mark.parametrize('value,expected', (
    (0, b'\0'),
    (127, b'\x7f'),
    (128, b'\x81\x00'),
    (65535, b'\x83\xff\x7f'),
))
def test_encode_vlq_basic(value, expected):
    assert varints.encode_integer_vlq(value) == expected


def test_encode_vlq_negative_crashes():
    """Passing a negative value to the VLQ encoder must always fail."""
    with pytest.raises(ValueError):
        varints.encode_integer_vlq(-1)


@pytest.mark.parametrize('serialized,expected', (
    (b'\0', 0),
    (b'\x7f', 127),
    (b'\x81\x00', 128),
    (b'\x83\xff\x7f', 65535),
))
def test_decode_vlq_basic(serialized, expected):
    buf = bitstring.BitStream(bytes=serialized)
    assert varints.decode_integer_vlq(buf) == expected
    assert buf.pos == len(serialized) * 8, "Buffer wasn't emptied."


@pytest.mark.parametrize('value,expected', (
    (0, b'\0'),
    (1, b'\x02'),
    (-1, b'\x01'),
    (-2, b'\x03'),
    (2147483647, b'\xfe\xff\xff\xff\x0f'),
    (-2147483648, b'\xff\xff\xff\xff\x0f'),
))
def test_encode_zigzag_basic(value, expected):
    assert varints.encode_integer_zigzag(value) == expected


@pytest.mark.parametrize('serialized,expected', (
    (b'\0', 0),
    (b'\x02', 1),
    (b'\x01', -1),
    (b'\x03', -2),
    (b'\xfe\xff\xff\xff\x0f', 2147483647),
    (b'\xff\xff\xff\xff\x0f', -2147483648),
))
def test_decode_zigzag(serialized, expected):
    buf = bitstring.BitStream(bytes=serialized)
    assert varints.decode_integer_zigzag(buf) == expected
    assert buf.pos == len(serialized) * 8, "Buffer wasn't emptied."


@pytest.mark.parametrize('value,expected', (
    (0, b'\0'),
    (1, b'\x01'),
    (-32767, b'\xc1\xff\x7f'),
    (895484, b'\xb6\xd3\x7c'),
))
def test_encode_compact(value, expected):
    assert varints.encode_integer_compact(value) == expected


@pytest.mark.parametrize('serialized,expected', (
    (b'\0', 0),
    (b'\x01', 1),
    (b'\x41', -1),
    (b'\xc1\xff\x7f', -32767),
    (b'\xb6\xd3\x7c', 895484),
))
def test_decode_compact(serialized, expected):
    buf = bitstring.BitStream(bytes=serialized)
    assert varints.decode_integer_compact(buf) == expected
    assert buf.pos == len(serialized) * 8, "Buffer wasn't emptied."

# --11 0110 -101 0011 -111 1100
# B    6    D    3    F    C

# --000001 -1111111 -1111111
# 1100 0001 1111 1111 0111 1111
# 8    1    F    F    7    F
