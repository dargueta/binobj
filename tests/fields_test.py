"""Tests for fields."""

import io

import pytest

from binobj import errors
from binobj import fields
from binobj import varints
from binobj.serialization import DEFAULT
from binobj.serialization import UNDEFINED
from binobj import structures


def test_load__null_with_null_value():
    null_value = b' :( '
    field = fields.Bytes(name='field', size=4, null_value=null_value)
    assert field.load(io.BytesIO(null_value)) is None


def test_loads__field_insufficient_data():
    """Load a field when there's insufficient data -> BOOM"""
    with pytest.raises(errors.UnexpectedEOFError):
        fields.String(size=17).loads(b'abc')


def test_dump__null_with_null_value():
    """Dumping None should use null_value"""
    field = fields.Bytes(name='field', size=4, null_value=b' :( ')
    assert field.dumps(None) == b' :( '


def test_dump__null_with_default_null():
    """No defined ``null_value`` --> dumps all null bytes."""
    field = fields.Bytes(name='field', size=4, null_value=DEFAULT)
    assert field.dumps(None) == b'\0\0\0\0'


def test_dump__null_with_no_def_and_varlen():
    """Crash if trying to write ``None`` when ``null_value`` is undefined and
    column is variable-length."""
    field = fields.VariableLengthInteger(name='field',
                                         encoding=varints.VarIntEncoding.ZIGZAG)

    with pytest.raises(errors.UnserializableValueError):
        field.dumps(None)


def test_dump__allow_null_false_crashes():
    """Crash if we try dumping None and allow_null is False."""
    field = fields.Bytes(name='field', size=4, allow_null=False)

    with pytest.raises(errors.UnserializableValueError) as errinfo:
        field.dumps(None)

    assert errinfo.value.field is field
    assert errinfo.value.value is None


def test_dump__allow_null_false_with_null_value_crashes():
    """We still shouldn't be able to dump None if allow_null is false and
    null_value is provided."""
    field = fields.Bytes(name='field', size=4, allow_null=False,
                         null_value=b' :) ')

    with pytest.raises(errors.UnserializableValueError) as errinfo:
        field.dumps(None)

    assert errinfo.value.field is field
    assert errinfo.value.value is None


def test_dump__field_only__no_value_no_default():
    """Dumping a field with no predefined value crashes"""
    field = fields.Bytes(name='field', size=4)

    with pytest.raises(errors.MissingRequiredValueError):
        field.dumps()


def test_array__basic():
    """Test deserializing a list of stuff."""
    sequence = fields.Array(fields.UInt8())
    result = sequence.loads(b'\xde\xad\xbe\xef')
    assert result == [0xde, 0xad, 0xbe, 0xef]


def test_array__basic_sized():
    """Verify the behavior of a fixed-size array."""
    sequence = fields.Array(fields.UInt8(), count=3)
    result = sequence.loads(b'\xde\xad\xbe')
    assert result == [0xde, 0xad, 0xbe]


def test_array__sentinel():
    """Test deserializing a sequence that has a sentinel terminator."""
    halt = lambda _seq, _str, loaded, _ctx: loaded and (loaded[-1] == 0xdead)
    sequence = fields.Array(fields.UInt16(endian='little'), halt_check=halt)

    result = sequence.loads(b'\x00\x00\xff\x00\xad\xde\xff\xff', exact=False)
    assert result == [0, 0xff, 0xdead]


class BasicStructWithArray(structures.Struct):
    """A basic structure with a sized array."""
    header = fields.Bytes(const=b'ABC')
    numbers = fields.Array(fields.UInt16(endian='big'), count=2)
    trailer = fields.Bytes(const=b'XYZ')


def test_load__invalid_const():
    data = b'ASDFGHJXYZ'

    with pytest.raises(errors.ValidationError) as errinfo:
        BasicStructWithArray.from_bytes(data)

    assert errinfo.value.field is BasicStructWithArray.header
    assert errinfo.value.value == b'ASD'


def test_array__fixed_in_struct():
    """Test a fixed array in a struct with elements surrounding it."""
    stream = io.BytesIO(b'ABC\xde\xad\xbe\xefXYZ')
    struct = BasicStructWithArray.from_stream(stream)

    assert struct.header == b'ABC'
    assert struct.numbers == [0xdead, 0xbeef]
    assert struct.trailer == b'XYZ'


def bswsa_should_halt(seq, stream, loaded, context):   # pylint: disable=unused-argument
    """Halting function for :attr:`BasicStructWithSentinelArray.numbers`."""
    if loaded and loaded[-1] == 0:
        # Hit sentinel, remove it from the end of the array.
        del loaded[-1]
        return True
    return False


class BasicStructWithSentinelArray(structures.Struct):
    numbers = fields.Array(fields.UInt8(), halt_check=bswsa_should_halt)
    eof = fields.String(const='ABC')


def test_array__variable_in_struct():
    stream = io.BytesIO(b'\x01\x02\x7f\x00ABC')
    loaded = BasicStructWithSentinelArray.from_stream(stream)

    assert loaded.numbers == [1, 2, 0x7f]
    assert loaded.eof == 'ABC'


def test_array__dump_basic():
    struct = BasicStructWithSentinelArray(numbers=[1, 2, 3, 0])
    assert struct.to_bytes() == b'\x01\x02\x03\x00ABC'


def test_descriptor_get():
    """A field should return itself when accessed from a class, and its assigned
    value when accessed from an instance."""
    assert isinstance(BasicStructWithArray.header, fields.Bytes)

    struct = BasicStructWithArray(header=b'abc')
    assert struct.header == b'abc'


def test_descriptor_set():
    """Setting a field on an instance should update values."""
    instance = BasicStructWithArray()

    assert 'numbers' not in instance.__values__
    instance.numbers = [1, 2]
    assert 'numbers' in instance.__values__, 'Value was not set in instance'
    assert instance.__values__['numbers'] == [1, 2]


def test_descriptor_delete__no_default_to_undefined():
    """Deleting a field should set it to its default value, or UNDEFINED."""
    instance = BasicStructWithArray()

    assert 'numbers' not in instance.__values__

    instance.numbers = [1, 2]
    assert 'numbers' in instance.__values__
    assert instance.__values__['numbers'] == [1, 2]

    del instance.numbers
    assert instance.numbers is UNDEFINED


def test_descriptor_delete__const_to_const():
    """Deleting a const field should have no effect."""
    instance = BasicStructWithArray()

    assert 'header' not in instance.__values__
    assert instance.header == b'ABC'
    assert 'header' in instance.__values__
    assert instance.__values__['header'] == b'ABC'

    del instance.header

    # Check to see if 'header' is in __values__ first because accessing 'header'
    # from the instance will automatically set it in the dictionary.
    assert 'header' in instance.__values__
    assert instance.__values__['header'] == b'ABC'
    assert instance.header == b'ABC'


def test_string__load_basic():
    """Basic test of loading a String"""
    field = fields.String(size=13, encoding='utf-8')
    assert field.loads(b'\xc2\xaf\\_(\xe3\x83\x84)_/\xc2\xaf') == r'¯\_(ツ)_/¯'


def test_string__dump_basic():
    """Basic test of dumping a String"""
    field = fields.String(size=13, encoding='utf-8')
    assert field.dumps(r'¯\_(ツ)_/¯') == b'\xc2\xaf\\_(\xe3\x83\x84)_/\xc2\xaf'


def test_string__dump_too_long_before_encoding():
    """Basic test of dumping a string that's too long into a String."""
    field = fields.String(size=5, encoding='utf-8')
    with pytest.raises(errors.ValueSizeError):
        assert field.dumps('abcdefg')


def test_string__dump_to_long_after_encoding():
    """Test dumping a string that's too long only after encoding to bytes."""
    field = fields.String(size=4, encoding='utf-8')
    with pytest.raises(errors.ValueSizeError):
        assert field.dumps('très')


def test_string__dump_too_short_before_encoding():
    """Basic test of dumping a string that's too short into a String."""
    field = fields.String(size=5, encoding='utf-8')
    with pytest.raises(errors.ValueSizeError):
        assert field.dumps('a')


def test_stringz__load_basic():
    """Basic test of StringZ loading."""
    field = fields.StringZ(encoding='utf-8')
    assert field.loads(b'\xc2\xaf\\_(\xe3\x83\x84)_/\xc2\xaf\0') == r'¯\_(ツ)_/¯'


def test_stringz__load_eof_before_null():
    """Crash if we hit the end of the data before we get a null byte."""
    field = fields.StringZ(encoding='utf-8')
    with pytest.raises(errors.UnexpectedEOFError):
        assert field.loads(b'\xc2\xaf\\_(\xe3\x83\x84)_/\xc2\xaf')


def test_stringz__dump_basic():
    """Basic test of StringZ dumping."""
    field = fields.StringZ(encoding='utf-8')
    assert field.dumps(r'¯\_(ツ)_/¯') == b'\xc2\xaf\\_(\xe3\x83\x84)_/\xc2\xaf\0'


def test_varint__signed_crash():
    """Crash when creating a signed variable-length integer using an encoding
    that doesn't support signed values."""
    with pytest.raises(errors.FieldConfigurationError) as errinfo:
        fields.VariableLengthInteger(encoding=varints.VarIntEncoding.VLQ)

    assert str(errinfo.value).startswith("Signed integers can't be encoded")


def test_varint__unsupported_encoding():
    """Crash if we try using an unsupported VarInt encoding."""
    with pytest.raises(errors.FieldConfigurationError) as errinfo:
        fields.VariableLengthInteger(encoding='uleb128')

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
    field = fields.VariableLengthInteger(encoding=varints.VarIntEncoding.VLQ,
                                         signed=False)
    assert field.dumps(value) == expected


@pytest.mark.parametrize('data, expected', (
    (b'\x3f', 0x3f),
))
def test_varint__basic_load(data, expected):
    """Test VLQ load."""
    field = fields.VariableLengthInteger(encoding=varints.VarIntEncoding.VLQ,
                                         signed=False)
    assert field.loads(data) == expected


def test_varint__overflow():
    """Crash if we try to zigzag an integer that's too big."""
    field = fields.VariableLengthInteger(encoding=varints.VarIntEncoding.ZIGZAG)

    with pytest.raises(errors.UnserializableValueError):
        field.dumps(2**65)


class SubStruct(structures.Struct):
    first = fields.UInt64(endian='big')
    second = fields.String(size=7)


class MainStruct(structures.Struct):
    before = fields.Int16(endian='big')
    nested = fields.Nested(SubStruct)
    after = fields.Int8()


def test_nested__load_basic():
    loaded = MainStruct.from_bytes(
        b'\x01\x02\x76\x54\x32\x10\xfe\xdc\xba\x98String!\x7f')

    assert loaded.before == 0x0102
    assert loaded.after == 0x7f
    assert loaded.nested.first == 0x76543210fedcba98
    assert loaded.nested.second == 'String!'


def test_nested__dump_basic():
    data = MainStruct(before=0x0bad, after=0x7f)
    data.nested = SubStruct(first=0x0fad, second='HllWrld')

    assert bytes(data) == b'\x0b\xad\x00\x00\x00\x00\x00\x00\x0f\xadHllWrld\x7f'
