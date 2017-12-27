"""Tests for the structure objects."""

# pylint: disable=invalid-name

import collections.abc
import io

import pytest

import binobj


class BasicStruct(binobj.Struct):
    """A basic structure."""
    string = binobj.String(size=7)
    int64 = binobj.Int64(endian='big')
    uint24 = binobj.UnsignedInteger(size=3, endian='little')


def test_basic__fields_loaded():
    """Ensure that the metaclass adds and marks fields properly."""
    assert hasattr(BasicStruct, '__components__'), 'Field dict missing.'
    field_list = tuple(BasicStruct.__components__.values())
    assert len(field_list) == 3

    assert field_list[0].name == 'string'
    assert field_list[0].index == 0
    assert field_list[0].offset == 0
    assert field_list[0].struct_class is not None, "Struct reference isn't set."

    assert field_list[1].name == 'int64'
    assert field_list[1].index == 1
    assert field_list[1].offset == 7
    assert field_list[1].struct_class is not None, "Struct reference isn't set."

    assert field_list[2].name == 'uint24'
    assert field_list[2].index == 2
    assert field_list[2].offset == 15
    assert field_list[2].struct_class is not None, "Struct reference isn't set."


def test_load__basic():
    stream = io.BytesIO(b'abcdefg\0\xba\xdc\x0f\xfe\xe1\x5b\xad\x01\x02\x03')
    values = BasicStruct().load(stream)

    assert isinstance(values, collections.abc.Mapping)

    assert 'string' in values
    assert values['string'] == 'abcdefg'
    assert 'int64' in values
    assert values['int64'] == 0x00badc0ffee15bad
    assert 'uint24' in values
    assert values['uint24'] == 0x030201


def test_load__short_read():
    """Crash if we don't have enough data to read all the fields."""
    stream = io.BytesIO(b'abcdefg\0\xba\xdc\x0f\xfe\xe1\x5b\xad\x01')

    with pytest.raises(binobj.UnexpectedEOFError) as errinfo:
        BasicStruct().load(stream)

    exc = errinfo.value
    assert exc.field is BasicStruct.uint24
    assert exc.offset == BasicStruct.uint24.offset
    assert exc.size == 3


def test_partial_load__bad_column():
    """Crash if an invalid column name is given."""
    stream = io.BytesIO(b'zyxwvut\0\xba\xdc\x0f\xfe\xe1\x5b\xad\x01')

    with pytest.raises(ValueError) as errinfo:
        BasicStruct().partial_load(stream, 'lol')

    assert str(errinfo.value) == "BasicStruct doesn't have a field named 'lol'."


def test_partial_load__short_read():
    """A short read with no defined end field shouldn't crash partial_load()."""
    stream = io.BytesIO(b'zyxwvut\0\xba\xdc\x0f\xfe\xe1\x5b\xad\x01')

    # Make sure the correct data was loaded and that the last field was *not*
    # included in the output.
    loaded = BasicStruct().partial_load(stream)
    assert loaded == {
        'string': 'zyxwvut',
        'int64': 0x00badc0ffee15bad
    }

    # Stream head should've been repositioned properly as well.
    assert stream.tell() == BasicStruct.uint24.offset
    assert stream.read() == b'\x01'


def test_partial_load__stops():
    """Verify partial_load() stops at the right field."""
    stream = io.BytesIO(b'zyxwvut\0\xba\xdc\x0f\xfe\xe1\x5b\xad\x01\x02\x03extra data!')

    # int64 should be the last field included in the output.
    loaded = BasicStruct().partial_load(stream, 'int64')
    assert loaded == {
        'string': 'zyxwvut',
        'int64': 0x00badc0ffee15bad,
    }

    # Stream head should be at the beginning of the first unread field.
    assert stream.tell() == BasicStruct.uint24.offset
    assert stream.read() == b'\x01\x02\x03extra data!'


def test_partial_load__short_read_of_required():
    """Crash if we get a short read on a required field."""
    stream = io.BytesIO(b'zyxwvut\x0b\xad')

    # int64 should be the last field included in the output.
    with pytest.raises(binobj.UnexpectedEOFError):
        BasicStruct().partial_load(stream, 'int64')


def test_get_field__basic():
    """Retrieve a field."""
    stream = io.BytesIO(b'zyxwvut\0\xba\xdc\x0f\xfe\xe1\x5b\xad')
    struct = BasicStruct()

    assert struct.get_field(stream, 'int64') == 0x00badc0ffee15bad
    assert stream.tell() == 0, 'Stream head was moved! :('

    assert struct.get_field(stream, 'string') == 'zyxwvut'
    assert stream.tell() == 0


def test_dump__basic():
    """Verify basic dump works."""
    data = {
        'string': 'AbCdEfG',
        'int64': -100,
        'uint24': 65535
    }
    output = BasicStruct().dumps(data)
    assert output == b'AbCdEfG\xff\xff\xff\xff\xff\xff\xff\x9c\xff\xff\0'


@pytest.mark.parametrize('extra_fields', (
    {'one'},
    {'one', 'two'},
))
def test_dump__extra_fields(extra_fields):
    """Giving unrecognized fields will crash by default."""
    data = {
        'string': 'AbCdEfG',
        'int64': -100,
        'uint24': 65535,
    }

    # Add in the extra keys we can't keep
    data.update({k: 0 for k in extra_fields})

    with pytest.raises(binobj.UnexpectedValueError) as errinfo:
        BasicStruct().dumps(data)

    assert errinfo.value.names == extra_fields


def test_dump__missing_fields():
    """Crash if we're missing field a field without default values."""
    data = {
        'string': 'AbCdEfG',
        'uint24': 65535,
    }

    with pytest.raises(binobj.MissingRequiredValueError) as errinfo:
        BasicStruct().dumps(data)

    assert errinfo.value.field is BasicStruct.int64


def test_partial_dump__basic():
    """Test basic partial dump."""
    data = {
        'string': 'AbCdEfG',
        'int64': 65535,
    }
    struct = BasicStruct()
    stream = io.BytesIO()

    struct.partial_dump(stream, data)
    assert stream.getvalue() == b'AbCdEfG\0\0\0\0\0\0\xff\xff'

    stream.seek(0)
    stream.truncate()
    struct.partial_dump(stream, data, 'int64')
    assert stream.getvalue() == b'AbCdEfG\0\0\0\0\0\0\xff\xff'


def test_array__basic():
    """Test deserializing a list of stuff."""
    sequence = binobj.Array(binobj.UInt8())
    result = sequence.loads(b'\xde\xad\xbe\xef')
    assert result == [0xde, 0xad, 0xbe, 0xef]


def test_array__basic_sized():
    """Verify the behavior of a fixed-size array."""
    sequence = binobj.Array(binobj.UInt8(), count=3)
    result = sequence.loads(b'\xde\xad\xbe\xef')
    assert result == [0xde, 0xad, 0xbe]


def test_array__sentinel():
    """Test deserializing a sequence that has a sentinel terminator."""
    halt = lambda _seq, _str, loaded, _ctx: loaded and (loaded[-1] == 0xdead)
    sequence = binobj.Array(binobj.UInt16(endian='little'), halt_check=halt)

    result = sequence.loads(b'\x00\x00\xff\x00\xad\xde\xff\xff', exact=False)
    assert result == [0, 0xff, 0xdead]


class BasicStructWithArray(binobj.Struct):
    """A basic structure with a sized array."""
    class Options:
        endian = 'big'

    header = binobj.Bytes(const=b'ABC')
    numbers = binobj.Array(binobj.UInt16(), count=2)
    trailer = binobj.Bytes(const=b'XYZ')


def test_array__fixed_in_struct():
    """Test a fixed array in a struct with elements surrounding it."""
    stream = io.BytesIO(b'ABC\xde\xad\xbe\xefXYZ')
    loaded = BasicStructWithArray().load(stream)

    assert loaded == {
        'header': b'ABC',
        'numbers': [0xdead, 0xbeef],
        'trailer': b'XYZ',
    }
