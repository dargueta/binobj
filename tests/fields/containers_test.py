import io
import sys

import pytest

import binobj
from binobj import errors
from binobj import fields


class SubStruct(binobj.Struct):
    first = fields.UInt64(endian='big')
    second = fields.String(size=7)


class MainStruct(binobj.Struct):
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
    def halt(_seq, _str, values, **_extra):
        return values and (values[-1] == 0xdead)

    sequence = fields.Array(fields.UInt16(endian='little'), halt_check=halt)

    result = sequence.loads(b'\x00\x00\xff\x00\xad\xde\xff\xff', exact=False)
    assert result == [0, 0xff, 0xdead]


@pytest.mark.skipif(sys.version_info[:2] in ((3, 4), (3, 5)),
                    reason='Test is flaky on 3.4 and sometimes fails on 3.5.')
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


class BasicStructWithArray(binobj.Struct):
    header = fields.String(const='ABC')
    numbers = fields.Array(fields.UInt16(endian='big'), count=2)
    trailer = fields.String(const='XYZ')


def test_array__fixed_in_struct():
    """Test a fixed array in a struct with elements surrounding it."""
    stream = io.BytesIO(b'ABC\xde\xad\xbe\xefXYZ')
    struct = BasicStructWithArray.from_stream(stream)

    assert struct.header == 'ABC'
    assert struct.numbers == [0xdead, 0xbeef]
    assert struct.trailer == 'XYZ'


# pylint: disable=unused-argument
def bswsa_should_halt(seq, stream, values, context, loaded_fields):
    """Halting function for :attr:`BasicStructWithSentinelArray.numbers`."""
    if values and values[-1] == 0:
        # Hit sentinel, remove it from the end of the array.
        del values[-1]
        return True
    return False
# pylint: enable=unused-argument


class BasicStructWithSentinelArray(binobj.Struct):
    numbers = fields.Array(fields.UInt8(), halt_check=bswsa_should_halt)
    eof = fields.String(const='ABC')


def test_array__variable_length_sentinel_in_struct():
    stream = io.BytesIO(b'\x01\x02\x7f\x00ABC')
    loaded = BasicStructWithSentinelArray.from_stream(stream)

    assert loaded.numbers == [1, 2, 0x7f]
    assert loaded.eof == 'ABC'


class BasicStructWithArraySizeField(binobj.Struct):
    n_numbers = fields.UInt8()
    numbers = fields.Array(fields.UInt8(), count=n_numbers)
    eof = fields.String(const='ABC')


class BasicStructWithArraySizeFieldAsName(binobj.Struct):
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
    class _Crash(binobj.Struct):
        n_numbers = fields.UInt8()
        numbers = fields.Array(fields.UInt8(), count='eof')
        eof = fields.String(const='ABC')

    with pytest.raises(errors.FieldReferenceError):
        _Crash.from_bytes(b'\0\0ABC')


@pytest.mark.parametrize('count', (True, False, object()))
def test_array__bogus_count(count):
    with pytest.raises(TypeError):
        fields.Array(fields.UInt8(), count=count)


def test_array__dump_basic():
    struct = BasicStructWithSentinelArray(numbers=[1, 2, 3, 0])
    assert struct.to_bytes() == b'\x01\x02\x03\x00ABC'


class StructWithComputedSizeArray(binobj.Struct):
    half_size = fields.UInt8()
    size = fields.UInt8()
    stuff = fields.Array(fields.UInt8(), count=size)

    @size.computes
    def compute_size(self, all_fields):
        return all_fields['half_size'] * 2


def test_array__computed_size():
    """The array should still work if the size is computed."""
    struct = StructWithComputedSizeArray(half_size=3, stuff=[1, 1, 2, 3, 5, 8])
    assert struct.size == 6
    assert bytes(struct) == b'\x03\x06\x01\x01\x02\x03\x05\x08'


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
        },
    }

    struct = UnionContainer.from_bytes(b'\x01\x7f\x55\xaa')
    assert struct.to_dict() == {
        'data_type': 1,
        'item': {
            '_id': 0x7f,
            'other': 0xaa55,
        },
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


def test_union__field_class_crashes():
    """Passing a Field class to a Union should crash."""
    with pytest.raises(errors.ConfigurationError) as errinfo:
        fields.Union(fields.StringZ, load_decider=None, dump_decider=None)

    assert str(errinfo.value) == 'You must pass an instance of a Field, not a class.'
