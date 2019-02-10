import datetime
import math
import struct
import sys

import pytest

from binobj import errors
from binobj import varints
from binobj.fields import numeric


_PY_VER = tuple(sys.version_info[:2])


def test_integer_overflow():
    """An overflow error should be rethrown as a serialization error."""
    field = numeric.UInt16()
    with pytest.raises(errors.UnserializableValueError):
        field.dumps(65536)


def test_const_set_size__varint():
    """Variable integers should set their size when ``const`` is defined."""
    field = numeric.VariableLengthInteger(vli_format=varints.VarIntEncoding.VLQ,
                                          const=987654321)
    assert field.size == 5


def test_varint__unsupported_encoding():
    """Crash if we try using an unsupported VarInt encoding."""
    with pytest.raises(errors.ConfigurationError) as errinfo:
        numeric.VariableLengthInteger(vli_format='uleb128')

    assert str(errinfo.value).startswith('Invalid or unsupported integer')


def test_varint__underflow():
    """Crash if VLQ gets a negative number."""
    field = numeric.VariableLengthInteger(vli_format=varints.VarIntEncoding.VLQ)
    with pytest.raises(errors.UnserializableValueError):
        field.dumps(-1)


@pytest.mark.parametrize('value,expected', (
    (127, b'\x7f'),
    (0x1234567890, b'\x82\xa3\xa2\xd9\xf1\x10'),
))
def test_varint__basic_dump(value, expected):
    """Test VLQ dump.

    We know that our codecs work (see varints_test.py) so here we're doing a
    perfunctory test to make sure dumping works as expected.
    """
    field = numeric.VariableLengthInteger(vli_format=varints.VarIntEncoding.VLQ)
    assert field.dumps(value) == expected


@pytest.mark.parametrize('data, expected', (
    (b'\x3f', 0x3f),
))
def test_varint__basic_load(data, expected):
    """Test VLQ load."""
    field = numeric.VariableLengthInteger(vli_format=varints.VarIntEncoding.VLQ)
    assert field.loads(data) == expected


def test_varint__max_bytes():
    """Crash if a variable-length integer takes up too many bytes."""
    field = numeric.VariableLengthInteger(vli_format=varints.VarIntEncoding.VLQ,
                                          max_bytes=2)

    with pytest.raises(errors.ValueSizeError):
        field.dumps(100000)


def test_float_bad_endian_crashes():
    """Endianness must be either 'little' or 'big'."""
    with pytest.raises(ValueError):
        numeric.Float64(endian='broken')


@pytest.mark.parametrize('field_object, fmt_string', (
    (numeric.Float32(endian='little'), '<f'),
    (numeric.Float64(endian='little'), '<d'),
    (numeric.Float32(endian='big'), '>f'),
    (numeric.Float64(endian='big'), '>d'),
))
@pytest.mark.parametrize('value', (
    math.pi,
    math.inf,
    -math.inf,
    math.nan,
))
def test_float__dumps(value, field_object, fmt_string):
    assert field_object.dumps(value) == struct.pack(fmt_string, value)


@pytest.mark.parametrize('field_object, fmt_string', (
    (numeric.Float32(endian='little'), '<f'),
    (numeric.Float64(endian='little'), '<d'),
    (numeric.Float32(endian='big'), '>f'),
    (numeric.Float64(endian='big'), '>d'),
))
@pytest.mark.parametrize('value', (
    math.pi,
    math.inf,
    -math.inf,
))
def test_float__loads(value, field_object, fmt_string):
    assert field_object.loads(struct.pack(fmt_string, value)) == pytest.approx(value)


@pytest.mark.skipif(_PY_VER < (3, 6), reason='binary16 only supported on 3.6+')
def test_float16__loads():
    field = numeric.Float16(endian='little')
    result = field.loads(struct.pack('<e', math.e))
    assert math.isclose(result, math.e, rel_tol=0.001)


@pytest.mark.skipif(_PY_VER < (3, 6), reason='binary16 only supported on 3.6+')
def test_float16__dumps():
    field = numeric.Float16(endian='big')
    assert field.dumps(65504) == struct.pack('>e', 65504)


@pytest.mark.skipif(_PY_VER >= (3, 6), reason='binary16 supported on 3.6+')
def test_float16_crashes_on_35():
    with pytest.raises(ValueError, match=r'^binary16.*$'):
        numeric.Float16()


def test_float__loads__exception_translation(mocker):
    """:class:`struct.error` must be translated."""
    pack_mock = mocker.patch('binobj.fields.numeric.struct.unpack')
    pack_mock.side_effect = struct.error('Some error happened')

    with pytest.raises(errors.DeserializationError):
        numeric.Float32().loads(b'1234')


def test_float__dumps__exception_translation(mocker):
    """:class:`struct.error` must be translated."""
    pack_mock = mocker.patch('binobj.fields.numeric.struct.pack')
    pack_mock.side_effect = struct.error('Some error happened')

    with pytest.raises(errors.SerializationError):
        numeric.Float32().dumps(1234)


def test_timestamp__invalid_resolution():
    with pytest.raises(errors.ConfigurationError):
        numeric.Timestamp(size=4, resolution='Y')


@pytest.mark.parametrize('data,expected', (
    (b'\0\0\0\x80', datetime.datetime(1901, 12, 13, 20, 45, 52)),
    (b'\xff\xff\xff\x7f', datetime.datetime(2038, 1, 19, 3, 14, 7)),
))
def test_timestamp__loads__naive(data, expected):
    field = numeric.Timestamp32(endian='little')
    assert field.loads(data) == expected


def test_timestamp__loads__aware():
    field = numeric.Timestamp32(endian='little', tz_aware=True)
    loaded = field.loads(b'\x01\x23\x45\x67')
    assert loaded == datetime.datetime(
        2024, 11, 26, 1, 23, 13, tzinfo=datetime.timezone.utc)


def test_timestamp__loads__microseconds():
    field = numeric.Timestamp64(endian='big', resolution='us')
    loaded = field.loads(b'\x00\x05\x81\x85\x84\x32\xc1\xad')
    assert loaded == datetime.datetime(2019, 2, 10, 7, 55, 32, 105645)


def test_timestamp__roundtrip():
    field = numeric.Timestamp(size=12, resolution='us', tz_aware=True)
    now = datetime.datetime.now(datetime.timezone.utc)
    assert field.loads(field.dumps(now)) == now
