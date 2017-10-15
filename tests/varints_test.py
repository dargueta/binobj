"""Tests for the variable-length integers."""

import io

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
    assert varints.encode_integer_vlq(None, value) == expected


def test_encode_vlq_negative_crashes():
    """Passing a negative value to the VLQ encoder must always fail."""
    with pytest.raises(errors.UnserializableValueError):
        varints.encode_integer_vlq(None, -1)


@pytest.mark.parametrize('serialized,expected', (
    (b'\0', 0),
    (b'\x7f', 127),
    (b'\x81\x00', 128),
    (b'\x83\xff\x7f', 65535),
))
def test_decode_vlq_basic(serialized, expected):
    buf = io.BytesIO(serialized)
    assert varints.decode_integer_vlq(None, buf) == expected
    assert buf.tell() == len(serialized), "Buffer wasn't emptied."


def test_decode_vlq_too_few_bytes():
    """Too few bytes -> UnexpectedEOFError"""
    buf = io.BytesIO(b'\x83\xff')
    with pytest.raises(errors.UnexpectedEOFError):
        varints.decode_integer_vlq(None, buf)


@pytest.mark.parametrize('value,expected', (
    (0, b'\0'),
    (1, b'\x02'),
    (-1, b'\x01'),
    (-2, b'\x03'),
    (2147483647, b'\xfe\xff\xff\xff\x0f'),
    (-2147483648, b'\xff\xff\xff\xff\x0f'),
))
def test_encode_zigzag_basic(value, expected):
    assert varints.encode_integer_zigzag(None, value) == expected


@pytest.mark.parametrize('serialized,expected', (
    (b'\0', 0),
    (b'\x02', 1),
    (b'\x01', -1),
    (b'\x03', -2),
    (b'\xfe\xff\xff\xff\x0f', 2147483647),
    (b'\xff\xff\xff\xff\x0f', -2147483648),
))
def test_decode_zigzag(serialized, expected):
    buf = io.BytesIO(serialized)
    assert varints.decode_integer_zigzag(None, buf) == expected
    assert buf.tell() == len(serialized), "Buffer wasn't emptied."


def test_decode_zigzag_too_few_bytes():
    """Too few bytes -> UnexpectedEOFError"""
    buf = io.BytesIO(b'\xfe\xff\xff')
    with pytest.raises(errors.UnexpectedEOFError):
        varints.decode_integer_zigzag(None, buf)


@pytest.mark.parametrize('serialized,expected', (
    (b'\0', 0),
    (b'\x01', 1),
    (b'\x41', -1),
    (b'\x81\x00', 128),
    (b'\xc0\x7f', -127),
))
def test_decode_compact(serialized, expected):
    buf = io.BytesIO(serialized)
    assert varints.decode_integer_compact(None, buf) == expected
    assert buf.tell() == len(serialized), "Buffer wasn't emptied."


def test_decode_compact_too_few_bytes():
    """Too few bytes -> UnexpectedEOFError"""
    buf = io.BytesIO(b'\xc0\xff')
    with pytest.raises(errors.UnexpectedEOFError):
        varints.decode_integer_compact(None, buf)
