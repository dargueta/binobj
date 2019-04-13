"""Tests for the variable-length integers."""

import io

import pytest

from binobj import varints


@pytest.mark.parametrize(
    "value,expected",
    ((0, b"\0"), (127, b"\x7f"), (128, b"\x81\x00"), (65535, b"\x83\xff\x7f")),
)
def test_encode_vlq_basic(value, expected):
    assert varints.encode_integer_vlq(value) == expected


def test_encode_vlq_negative_crashes():
    """Passing a negative value to the VLQ encoder must always fail."""
    with pytest.raises(ValueError):
        varints.encode_integer_vlq(-1)


@pytest.mark.parametrize(
    "serialized,expected",
    ((b"\0", 0), (b"\x7f", 127), (b"\x81\x00", 128), (b"\x83\xff\x7f", 65535)),
)
def test_decode_vlq_basic(serialized, expected):
    buf = io.BytesIO(serialized)
    assert varints.decode_integer_vlq(buf) == expected
    assert buf.read() == b"", "Buffer wasn't emptied."


@pytest.mark.parametrize(
    "value,expected",
    ((0, b"\0"), (1, b"\x01"), (-32767, b"\xc1\xff\x7f"), (895484, b"\xb6\xd3\x7c")),
)
def test_encode_compact(value, expected):
    assert varints.encode_integer_compact(value) == expected


@pytest.mark.parametrize(
    "serialized,expected",
    (
        (b"\0", 0),
        (b"\x01", 1),
        (b"\x41", -1),
        (b"\xc1\xff\x7f", -32767),
        (b"\xb6\xd3\x7c", 895484),
    ),
)
def test_decode_compact(serialized, expected):
    buf = io.BytesIO(serialized)
    assert varints.decode_integer_compact(buf) == expected
    assert buf.read() == b"", "Buffer wasn't emptied."


@pytest.mark.parametrize(
    "value,expected",
    (
        (0, b"\0"),
        (127, b"\x7f"),
        (128, b"\x80\x01"),
        (7345004, b"\xec\xa6\xc0\x03"),
        (0xB1ACC0FFEE2BAD, b"\xad\xd7\xb8\xff\x8f\x98\xeb\x58"),
    ),
)
def test_encode_uleb128(value, expected):
    assert varints.encode_integer_uleb128(value) == expected


def test_encode_uleb128__negative_crashes():
    with pytest.raises(ValueError):
        assert varints.encode_integer_uleb128(-1)


@pytest.mark.parametrize(
    "serialized, expected",
    (
        (b"\0", 0),
        (b"\x7f", 127),
        (b"\xd2\x85\xd8\xcc\x04", 1234567890),
        (b"\xad\xd7\xb8\xff\x8f\x98\xeb\x58", 0xB1ACC0FFEE2BAD),
    ),
)
def test_decode_uleb128(serialized, expected):
    buf = io.BytesIO(serialized)
    assert varints.decode_integer_uleb128(buf) == expected
    assert buf.read() == b"", "Buffer wasn't emptied"


SIGNED_LEB_VALUES = [
    (0, b"\0"),
    (63, b"\x3f"),
    (64, b"\xc0\x00"),
    (126, b"\xfe\x00"),
    (127, b"\xff\x00"),
    (128, b"\x80\x01"),
    (-126, b"\x82\x7f"),
    (-127, b"\x81\x7f"),
    (-128, b"\x80\x7f"),
    (0xB1ACC0FFEE2BAD, b"\xad\xd7\xb8\xff\x8f\x98\xeb\xd8\x00"),
    (-0xB1ACC0FFEE2BAD, b"\xd3\xa8\xc7\x80\xf0\xe7\x94\xa7\x7f"),
]


@pytest.mark.parametrize("value,expected", SIGNED_LEB_VALUES)
def test_encode_signed_leb128(value, expected):
    assert varints.encode_integer_leb128(value) == expected


@pytest.mark.parametrize("value,serialized", SIGNED_LEB_VALUES)
def test_decode_signed_leb128(value, serialized):
    buf = io.BytesIO(serialized)
    assert varints.decode_integer_leb128(buf) == value
    assert buf.read() == b"", "Buffer wasn't emptied"
