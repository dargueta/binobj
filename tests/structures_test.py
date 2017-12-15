"""Tests for the structure objects."""

import collections.abc

import bitstring
import pytest

import binobj


class BasicStruct(binobj.Struct):
    """A basic structure."""
    string = binobj.String(n_bytes=7)
    int64 = binobj.Int64(endian='big')
    uint24 = binobj.UnsignedInteger(n_bytes=3, endian='little')


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
    assert field_list[1].offset == 56
    assert field_list[1].struct_class is not None, "Struct reference isn't set."

    assert field_list[2].name == 'uint24'
    assert field_list[2].index == 2
    assert field_list[2].offset == 120
    assert field_list[2].struct_class is not None, "Struct reference isn't set."


def test_load__basic():
    stream = bitstring.BitStream(bytes=b'abcdefg\0\xba\xdc\x0f\xfe\xe1\x5b\xad\x01\x02\x03')
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
    stream = bitstring.BitStream(bytes=b'abcdefg\0\xba\xdc\x0f\xfe\xe1\x5b\xad\x01')

    with pytest.raises(binobj.UnexpectedEOFError) as errinfo:
        BasicStruct().load(stream)

    exc = errinfo.value
    assert exc.field is BasicStruct.uint24
    assert exc.offset == BasicStruct.uint24.offset
    assert exc.size == 24


def test_partial_load__bad_column():
    """Crash if an invalid column name is given."""
    stream = bitstring.BitStream(bytes=b'zyxwvut\0\xba\xdc\x0f\xfe\xe1\x5b\xad\x01')

    with pytest.raises(ValueError) as errinfo:
        BasicStruct().partial_load(stream, 'lol')

    assert str(errinfo.value) == "BasicStruct doesn't have a field named 'lol'."


def test_partial_load__short_read():
    """A short read with no defined end field shouldn't crash partial_load()."""
    stream = bitstring.BitStream(bytes=b'zyxwvut\0\xba\xdc\x0f\xfe\xe1\x5b\xad\x01')

    # Make sure the correct data was loaded and that the last field was *not*
    # included in the output.
    loaded = BasicStruct().partial_load(stream)
    assert loaded == {
        'string': 'zyxwvut',
        'int64': 0x00badc0ffee15bad
    }

    # Stream head should've been repositioned properly as well.
    assert stream.pos == BasicStruct.uint24.offset
    assert stream[stream.pos:].tobytes() == b'\x01'


def test_partial_load__stops():
    """Verify partial_load() stops at the right field."""
    stream = bitstring.BitStream(
        bytes=b'zyxwvut\0\xba\xdc\x0f\xfe\xe1\x5b\xad\x01\x02\x03extra data!')

    # int64 should be the last field included in the output.
    loaded = BasicStruct().partial_load(stream, 'int64')
    assert loaded == {
        'string': 'zyxwvut',
        'int64': 0x00badc0ffee15bad,
    }

    # Stream head should be at the beginning of the first unread field.
    assert stream.pos == BasicStruct.uint24.offset
    assert stream[stream.pos:].tobytes() == b'\x01\x02\x03extra data!'


def test_partial_load__short_read_of_required():
    """Crash if we get a short read on a required field."""
    stream = bitstring.BitStream(bytes=b'zyxwvut\x0b\xad')

    # int64 should be the last field included in the output.
    with pytest.raises(binobj.UnexpectedEOFError):
        BasicStruct().partial_load(stream, 'int64')


def test_get_field__basic():
    """Retrieve a field."""
    stream = bitstring.BitStream(bytes=b'zyxwvut\0\xba\xdc\x0f\xfe\xe1\x5b\xad')
    struct = BasicStruct()

    assert struct.get_field(stream, 'int64') == 0x00badc0ffee15bad
    assert stream.pos == 0, 'Stream head was moved! :('

    assert struct.get_field(stream, 'string') == 'zyxwvut'
    assert stream.pos == 0


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
    stream = bitstring.BitStream()

    struct.partial_dump(stream, data)
    assert stream.tobytes() == b'AbCdEfG\0\0\0\0\0\0\xff\xff'

    stream.clear()
    struct.partial_dump(stream, data, 'int64')
    assert stream.tobytes() == b'AbCdEfG\0\0\0\0\0\0\xff\xff'


def test_sequence__basic():
    """Test deserializing a list of stuff."""
    sequence = binobj.SerializableSequence(binobj.UInt8())
    result = sequence.loads(b'\xde\xad\xbe\xef')
    assert result == [0xde, 0xad, 0xbe, 0xef]


def test_sequence__sentinel():
    """Test deserializing a sequence that has a sentinel terminator."""
    halt = lambda _seq, _str, loaded, _ctx: loaded and (loaded[-1] == 0xdead)
    sequence = binobj.SerializableSequence(binobj.UInt16(endian='little'),
                                           halt_check=halt)

    result = sequence.loads(b'\x00\x00\xff\x00\xad\xde\xff\xff', exact=False)
    assert result == [0, 0xff, 0xdead]
