"""Tests for fields."""

import io
import sys

import pytest

import binobj
from binobj import errors
from binobj import fields
from binobj import varints
from binobj import structures
from binobj.fields import DEFAULT


def test_load__null_with_null_value():
    null_value = b' :( '
    field = fields.Bytes(name='field', size=4, null_value=null_value)
    assert field.allow_null is True
    assert field.load(io.BytesIO(null_value)) is None


def test_loads__field_insufficient_data():
    """Load a field when there's insufficient data -> BOOM"""
    with pytest.raises(errors.UnexpectedEOFError):
        fields.String(size=17).loads(b'abc')


def test_dump__null_with_null_value():
    """Dumping None should use null_value"""
    field = fields.Bytes(name='field', size=4, null_value=b' :( ')
    assert field.allow_null is True
    assert field.dumps(None) == b' :( '


def test_dump__null_with_default_null():
    """No defined ``null_value`` --> dumps all null bytes."""
    field = fields.Bytes(name='field', size=4, null_value=DEFAULT)
    assert field.dumps(None) == b'\0\0\0\0'


def test_dump__null_with_default_and_varlen():
    """Crash if trying to write ``None`` when using the default null_value and
    column is of variable length."""
    field = fields.StringZ(name='field', null_value=DEFAULT)
    assert field.allow_null is True

    with pytest.raises(errors.UnserializableValueError):
        field.dumps(None)


def test_dump__no_null_value_crashes():
    """Crash if we try dumping None with no null_value set."""
    field = fields.Bytes(name='field', size=4)
    assert not field.allow_null

    with pytest.raises(errors.UnserializableValueError) as errinfo:
        field.dumps(None)

    assert errinfo.value.field is field
    assert errinfo.value.value is None


def test_dump__allow_null_correctly_set():
    """We still shouldn't be able to dump None if allow_null is false and
    null_value is provided."""
    field = fields.Bytes(name='field', size=4, null_value=b' :) ')
    assert field.allow_null is True

    field = fields.Bytes(name='field', size=4)
    assert field.allow_null is False


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
    halt = lambda _seq, _str, values, context, loaded_fields: values and (values[-1] == 0xdead)
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


# pylint: disable=unused-argument
def bswsa_should_halt(seq, stream, values, context, loaded_fields):
    """Halting function for :attr:`BasicStructWithSentinelArray.numbers`."""
    if values and values[-1] == 0:
        # Hit sentinel, remove it from the end of the array.
        del values[-1]
        return True
    return False
# pylint: enable=unused-argument


class BasicStructWithSentinelArray(structures.Struct):
    numbers = fields.Array(fields.UInt8(), halt_check=bswsa_should_halt)
    eof = fields.String(const='ABC')


def test_array__variable_length_sentinel_in_struct():
    stream = io.BytesIO(b'\x01\x02\x7f\x00ABC')
    loaded = BasicStructWithSentinelArray.from_stream(stream)

    assert loaded.numbers == [1, 2, 0x7f]
    assert loaded.eof == 'ABC'


class BasicStructWithArraySizeField(structures.Struct):
    n_numbers = fields.UInt8()
    numbers = fields.Array(fields.UInt8(), count=n_numbers)
    eof = fields.String(const='ABC')


class BasicStructWithArraySizeFieldAsName(structures.Struct):
    n_numbers = fields.UInt8()
    numbers = fields.Array(fields.UInt8(), count='n_numbers')
    eof = fields.String(const='ABC')


@pytest.mark.parametrize('cls', (
    BasicStructWithArraySizeField, BasicStructWithArraySizeFieldAsName))
def test_array__variable_length_size_in_struct(cls):
    stream = io.BytesIO(b'\x03\x01\x02\x7fABC')
    loaded = cls.from_stream(stream)

    assert loaded.numbers == [1, 2, 0x7f]
    assert loaded.eof == 'ABC'


def test_array__variable_length_forward_reference_crashes():
    """A forward reference to a field must crash."""
    class _Crash(structures.Struct):
        n_numbers = fields.UInt8()
        numbers = fields.Array(fields.UInt8(), count='eof')
        eof = fields.String(const='ABC')

    with pytest.raises(errors.FieldReferenceError):
        _Crash.from_bytes(b'\0\0ABC')


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


def test_string__dump_too_long_after_encoding():
    """Test dumping a string that's too long only after encoding to bytes."""
    field = fields.String(size=4, encoding='utf-8')
    with pytest.raises(errors.ValueSizeError):
        assert field.dumps('très')


def test_string__dump_too_short_before_encoding():
    """Basic test of dumping a string that's too short into a String."""
    field = fields.String(size=5, encoding='utf-8')
    with pytest.raises(errors.ValueSizeError):
        assert field.dumps('a')


def test_string__dump_too_short_before_encoding__pad():
    """Dumping a string that's too short before encoding is okay."""
    field = fields.String(size=5, pad_byte=b' ')
    assert field.dumps('a') == b'a    '


def test_string__dump_too_short_after_encoding__pad():
    """Dumping a string that's too short but uses padding is okay."""
    field = fields.String(size=8, pad_byte=b'\0', encoding='utf-32-be')
    assert field.dumps('a') == b'\0\0\0a\0\0\0\0'


def test_string__dump_too_long_before_encoding__pad():
    """``pad_byte`` shouldn't prevent a crash if a string is too long."""
    field = fields.String(size=5, pad_byte=b'?')
    with pytest.raises(errors.ValueSizeError):
        field.dumps('abcdefgh')


def test_string__dump_too_long_after_encoding__pad():
    """``pad_byte`` shouldn't prevent a crash if a string is too long after
    encoding it."""
    field = fields.String(size=3, pad_byte=b'?', encoding='utf-16-le')
    with pytest.raises(errors.ValueSizeError):
        field.dumps('ab')


def test_string__pad_byte_wrong_type():
    """Trying to pass a regular string as pad_byte will explode."""
    with pytest.raises(TypeError):
        fields.String(size=4, pad_byte=' ')


def test_string__pad_byte_too_long():
    """The padding byte must be exactly one byte."""
    with pytest.raises(ValueError):
        fields.String(size=4, pad_byte=b'0123')


def test_string__pad_default():
    """The default value should be padded if necessary."""
    field = fields.String(size=4, pad_byte=b' ', default='?')
    assert field.dumps() == b'?   '


def test_stringz__load_basic():
    """Basic test of StringZ loading."""
    field = fields.StringZ(encoding='utf-8')
    assert field.loads(b'\xc2\xaf\\_(\xe3\x83\x84)_/\xc2\xaf\0') == r'¯\_(ツ)_/¯'


def test_stringz__load_eof_before_null():
    """Crash if we hit the end of the data before we get a null byte."""
    field = fields.StringZ(encoding='utf-8')
    with pytest.raises(errors.DeserializationError):
        assert field.loads(b'\xc2\xaf\\_(\xe3\x83\x84)_/\xc2\xaf')


def test_stringz__dump_basic():
    """Basic test of StringZ dumping."""
    field = fields.StringZ(encoding='utf-8')
    assert field.dumps(r'¯\_(ツ)_/¯') == b'\xc2\xaf\\_(\xe3\x83\x84)_/\xc2\xaf\0'


def test_stringz__dump_multibyte():
    """Basic multibyte test dump."""
    field = fields.StringZ(encoding='utf-32-le')
    assert field.dumps('AbC') == b'A\x00\x00\x00b\x00\x00\x00C\x00\x00\x00\x00\x00\x00\x00'


def test_stringz__dump_multibyte_with_bom():
    """Ensure multibyte encodings work with StringZ as well and the BOM isn't
    added before the null byte."""
    field = fields.StringZ(encoding='utf-16')

    if sys.byteorder == 'little':
        assert field.dumps('AbCd') == b'\xff\xfeA\x00b\x00C\x00d\x00\x00\x00'
    else:
        assert field.dumps('AbCd') == b'\xfe\xff\x00A\x00b\x00C\x00d\x00\x00'


def test_stringz_load_multibyte():
    """Test loading multibyte strings with a terminating null."""
    field = fields.StringZ(encoding='utf-16')
    assert field.loads(b'\xff\xfeA\x00b\x00C\x00d\x00\x00\x00') == 'AbCd'
    assert field.loads(b'\xfe\xff\x00A\x00b\x00C\x00d\x00\x00') == 'AbCd'


def test_varint__signed_crash():
    """Crash when creating a signed variable-length integer using an encoding
    that doesn't support signed values."""
    with pytest.raises(errors.ConfigurationError) as errinfo:
        fields.VariableLengthInteger(vli_format=varints.VarIntEncoding.VLQ)

    assert str(errinfo.value).startswith("Signed integers can't be encoded")


def test_varint__unsupported_encoding():
    """Crash if we try using an unsupported VarInt encoding."""
    with pytest.raises(errors.ConfigurationError) as errinfo:
        fields.VariableLengthInteger(vli_format='uleb128')

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
    field = fields.VariableLengthInteger(vli_format=varints.VarIntEncoding.VLQ,
                                         signed=False)
    assert field.dumps(value) == expected


@pytest.mark.parametrize('data, expected', (
    (b'\x3f', 0x3f),
))
def test_varint__basic_load(data, expected):
    """Test VLQ load."""
    field = fields.VariableLengthInteger(vli_format=varints.VarIntEncoding.VLQ,
                                         signed=False)
    assert field.loads(data) == expected


def test_varint__overflow():
    """Crash if we try to zigzag an integer that's too big."""
    field = fields.VariableLengthInteger(vli_format=varints.VarIntEncoding.ZIGZAG)

    with pytest.raises(errors.UnserializableValueError):
        field.dumps(2**65)


def test_varint__max_bytes():
    """Crash if a variable-length integer takes up too many bytes."""
    field = fields.VariableLengthInteger(vli_format=varints.VarIntEncoding.VLQ,
                                         signed=False, max_bytes=2)

    with pytest.raises(errors.ValueSizeError):
        field.dumps(100000)


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


def test_nested__dump_basic_as_dict():
    """Test dumping where we pass a dictionary for the nested value instead of a
    Struct instance.
    """
    data = MainStruct(before=0x0bad, after=0x7f,
                      nested={'first': 0x0fad, 'second': 'HllWrld'})
    assert bytes(data) == b'\x0b\xad\x00\x00\x00\x00\x00\x00\x0f\xadHllWrld\x7f'


def test_array__load_nested():
    """Try loading an array of structs."""
    field = fields.Array(fields.Nested(SubStruct), count=2)
    loaded = field.loads(b'\xc0\xff\xee\xde\xad\xbe\xef\x00ABCDEFG'
                         b'\xfa\xde\xdb\xed\xa5\x51\xed\x00HIJKLMN')
    assert loaded == [
        {'first': 0xc0ffeedeadbeef00, 'second': 'ABCDEFG'},
        {'first': 0xfadedbeda551ed00, 'second': 'HIJKLMN'},
    ]


def test_array__dump_nested():
    """Try dumping an array of structs."""
    field = fields.Array(fields.Nested(SubStruct), count=2)
    dumped = field.dumps([
        {'first': 0xc0ffeedeadbeef00, 'second': 'ABCDEFG'},
        {'first': 0xfadedbeda551ed00, 'second': 'HIJKLMN'},
    ])

    assert dumped == b'\xc0\xff\xee\xde\xad\xbe\xef\x00ABCDEFG' \
                     b'\xfa\xde\xdb\xed\xa5\x51\xed\x00HIJKLMN'


class UnionItemA(binobj.Struct):
    _id = fields.UInt8(const=0xff)
    value = fields.StringZ()


class UnionItemB(binobj.Struct):
    _id = fields.UInt8(const=0x7f)
    other = fields.UInt16(endian='little')


# pylint: disable=unused-argument
def struct_load_decider(stream, choices, context, loaded_fields):
    data_type_id = loaded_fields['data_type']
    return choices[data_type_id]


def struct_dump_decider(data, choices, context, all_fields):
    data_type_id = all_fields['data_type']
    return choices[data_type_id]
# pylint: enable=unused-argument


class UnionContainer(binobj.Struct):
    data_type = fields.UInt8()
    item = fields.Union(UnionItemA, UnionItemB, load_decider=struct_load_decider,
                        dump_decider=struct_dump_decider)


def test_union__structs__dump_basic():
    """Basic test of dumping the Union field type."""
    struct = UnionContainer(data_type=0, item={'value': 'asdf'})
    assert struct.to_bytes() == b'\0\xffasdf\0'

    struct = UnionContainer(data_type=1, item={'other': 0xaa55})
    assert struct.to_bytes() == b'\x01\x7f\x55\xaa'


def test_union__structs__load_basic():
    """Basic test of loading the Union field type."""
    struct = UnionContainer.from_bytes(b'\0\xffasdf\0')
    assert struct.to_dict() == {
        'data_type': 0,
        'item': {
            '_id': 0xff,
            'value': 'asdf',
        }
    }

    struct = UnionContainer.from_bytes(b'\x01\x7f\x55\xaa')
    assert struct.to_dict() == {
        'data_type': 1,
        'item': {
            '_id': 0x7f,
            'other': 0xaa55,
        }
    }


# pylint: disable=unused-argument
def fields_load_decider(stream, choices, context, loaded_fields):
    data_type_id = loaded_fields['data_type']
    return choices[data_type_id]


def fields_dump_decider(data, choices, context, all_fields):
    if isinstance(all_fields['item'], str):
        return choices[0]
    return choices[1]
# pylint: enable=unused-argument


class FieldsUnionContainer(binobj.Struct):
    data_type = fields.UInt8()
    item = fields.Union(fields.StringZ(),
                        fields.UInt16(endian='little'),
                        load_decider=fields_load_decider,
                        dump_decider=fields_dump_decider)


def test_union__fields__dump_basic():
    """Basic test of dumping the Union field type."""
    struct = FieldsUnionContainer(data_type=0, item='asdf')
    assert struct.to_bytes() == b'\0asdf\0'

    struct = FieldsUnionContainer(data_type=1, item=0xaa55)
    assert struct.to_bytes() == b'\x01\x55\xaa'


def test_union__fields__load_basic():
    """Basic test of loading the Union field type."""
    struct = FieldsUnionContainer.from_bytes(b'\0asdf\0')
    assert struct.to_dict() == {
        'data_type': 0,
        'item': 'asdf',
    }

    struct = FieldsUnionContainer.from_bytes(b'\x01\x55\xaa')
    assert struct.to_dict() == {
        'data_type': 1,
        'item': 0xaa55,
    }
