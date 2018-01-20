"""Tests for the structure objects."""

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

    assert field_list[1].name == 'int64'
    assert field_list[1].index == 1
    assert field_list[1].offset == 7

    assert field_list[2].name == 'uint24'
    assert field_list[2].index == 2
    assert field_list[2].offset == 15


def test_load__basic():
    stream = io.BytesIO(b'abcdefg\0\xba\xdc\x0f\xfe\xe1\x5b\xad\x01\x02\x03')
    struct = BasicStruct.from_stream(stream)

    assert struct.string == 'abcdefg'
    assert struct.int64 == 0x00badc0ffee15bad
    assert struct.uint24 == 0x030201


def test_load__short_read():
    """Crash if we don't have enough data to read all the fields."""
    stream = io.BytesIO(b'abcdefg\0\xba\xdc\x0f\xfe\xe1\x5b\xad\x01')

    with pytest.raises(binobj.errors.UnexpectedEOFError) as errinfo:
        BasicStruct.from_stream(stream)

    exc = errinfo.value
    assert exc.field is BasicStruct.uint24
    assert exc.offset == BasicStruct.uint24.offset
    assert exc.size == 3


def test_loads__extra_bytes():
    """Crash if we have too much data."""
    with pytest.raises(binobj.errors.ExtraneousDataError) as errinfo:
        BasicStruct.from_bytes(b'abcdefghijklmnopqrstuwxyz')

    exc = errinfo.value
    assert exc.offset == BasicStruct.uint24.offset + BasicStruct.uint24.size


def test_partial_load__bad_column():
    """Crash if an invalid column name is given."""
    stream = io.BytesIO(b'zyxwvut\0\xba\xdc\x0f\xfe\xe1\x5b\xad\x01')

    with pytest.raises(ValueError) as errinfo:
        BasicStruct.partial_load(stream, 'lol')

    assert str(errinfo.value) == "BasicStruct doesn't have a field named 'lol'."


def test_partial_load__short_read():
    """A short read with no defined end field shouldn't crash partial_load()."""
    stream = io.BytesIO(b'zyxwvut\0\xba\xdc\x0f\xfe\xe1\x5b\xad\x01')

    # Make sure the correct data was loaded and that the last field was *not*
    # included in the output.
    output = BasicStruct.partial_load(stream)
    assert output['string'] == 'zyxwvut'
    assert output['int64'] == 0x00badc0ffee15bad

    # Stream head should've been repositioned properly as well.
    assert stream.tell() == BasicStruct.uint24.offset
    assert stream.read() == b'\x01'


def test_partial_load__stops():
    """Verify partial_load() stops at the right field."""
    stream = io.BytesIO(b'zyxwvut\0\xba\xdc\x0f\xfe\xe1\x5b\xad\x01\x02\x03extra data!')

    # int64 should be the last field included in the output.
    loaded = BasicStruct().partial_load(stream, 'int64')
    assert loaded == BasicStruct(string='zyxwvut', int64=0x00badc0ffee15bad)

    # Stream head should be at the beginning of the first unread field.
    assert stream.tell() == BasicStruct.uint24.offset
    assert stream.read() == b'\x01\x02\x03extra data!'


def test_partial_load__short_read_of_required():
    """Crash if we get a short read on a required field."""
    stream = io.BytesIO(b'zyxwvut\x0b\xad')

    # int64 should be the last field included in the output.
    with pytest.raises(binobj.errors.UnexpectedEOFError):
        BasicStruct.partial_load(stream, 'int64')


def test_get_field__basic():
    """Retrieve a field."""
    stream = io.BytesIO(b'zyxwvut\0\xba\xdc\x0f\xfe\xe1\x5b\xad')

    assert BasicStruct.get_field(stream, 'int64') == 0x00badc0ffee15bad
    assert stream.tell() == 0, 'Stream head was moved! :('

    assert BasicStruct.get_field(stream, 'string') == 'zyxwvut'
    assert stream.tell() == 0


def test_get_field__bad_name():
    with pytest.raises(ValueError) as errinfo:
        BasicStruct.get_field(None, ':)')

    assert str(errinfo.value) == "BasicStruct doesn't have a field named ':)'."


def test_dump__basic():
    """Verify basic dump works."""
    struct = BasicStruct(string='AbCdEfG', int64=-100, uint24=65535)
    output = struct.to_bytes()
    assert output == b'AbCdEfG\xff\xff\xff\xff\xff\xff\xff\x9c\xff\xff\0'


@pytest.mark.parametrize('extra_fields', (
    {'one'},
    {'one', 'two'},
))
def test_dump__extra_fields(extra_fields):
    """Giving unrecognized fields will crash by default."""
    with pytest.raises(binobj.errors.UnexpectedValueError) as errinfo:
        BasicStruct(string='AbCdEfG', int64=-100, uint24=65535,
                    **{k: 0 for k in extra_fields})

    assert errinfo.value.names == extra_fields


def test_dump__missing_fields():
    """Crash if we're missing field a field without default values."""
    struct = BasicStruct(string='AbCdEfG', uint24=65535)

    with pytest.raises(binobj.errors.MissingRequiredValueError) as errinfo:
        struct.to_bytes()

    assert errinfo.value.field is BasicStruct.int64


class BasicStructWithDefaults(binobj.Struct):
    string = binobj.String(size=7)
    int64 = binobj.Int64(endian='big', default=0)
    uint24 = binobj.UnsignedInteger(size=3, endian='little')


def test_partial_dump__full():
    """Test basic partial dump with all fields present or with defaults."""
    struct = BasicStructWithDefaults(string='AbCdEfG', uint24=65535)
    stream = io.BytesIO()

    struct.partial_dump(stream)
    assert stream.getvalue() == b'AbCdEfG\0\0\0\0\0\0\0\0\xff\xff\0'


def test_partial_dump__missing_last():
    """Ensure proper behavior if we're missing the last field."""
    struct = BasicStructWithDefaults(string='AbCdEfG')
    stream = io.BytesIO()

    struct.partial_dump(stream)
    assert stream.getvalue() == b'AbCdEfG\0\0\0\0\0\0\0\0'


def test_partial_dump__include_trailing_default():
    """Should still dump the last field if it's missing but has a default."""
    struct = BasicStructWithDefaults(string='AbCdEfG', uint24=65535)
    stream = io.BytesIO()

    struct.partial_dump(stream, 'int64')
    assert stream.getvalue() == b'AbCdEfG\0\0\0\0\0\0\0\0'
