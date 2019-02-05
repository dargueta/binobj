import struct

import pytest

from binobj import errors
from binobj import varints
from binobj.fields import numeric


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
    3.141592654,
    float('inf'),
    -float('inf'),
    float('nan'),
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
    3.141592654,
    float('inf'),
    -float('inf'),
))
def test_float__loads(value, field_object, fmt_string):
    assert field_object.loads(struct.pack(fmt_string, value)) == pytest.approx(value)


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
