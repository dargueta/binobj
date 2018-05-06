"""Basic tests for serialization code."""

import collections
import copy
import sys

import pytest

import binobj
from binobj import errors


def test_sentinels_are_singletons():
    """Verify deep copying works on sentinels.

    Deep copying, at least on some versions of Python, is implemented via
    pickling and then unpickling the container. If the sentinel class isn't
    implemented properly, we could end up with two sentinel objects that map to
    ``UNDEFINED`` or ``DEFAULT``.
    """
    dct = {'key': binobj.UNDEFINED}
    copied_dict = copy.deepcopy(dct)
    assert copied_dict['key'] is binobj.UNDEFINED


def test_dump__unserializable():
    field = binobj.Bytes(name='field', size=4)
    garbage = object()

    with pytest.raises(errors.UnserializableValueError) as errinfo:
        field.dumps(garbage)

    assert "can't serialize value of type 'object'." in str(errinfo.value)
    assert errinfo.value.field is field
    assert errinfo.value.value is garbage


def test_dump__use_default_value():
    """Test dumping when the default value is a constant."""
    field = binobj.UInt32(name='field', default=0xdeadbeef, endian='big')
    assert field.dumps() == b'\xde\xad\xbe\xef'


def test_dump__use_default_callable():
    """Test dumping when the default value is a callable."""
    field = binobj.UInt32(name='field', default=lambda: 0x1234, endian='big')
    assert field.dumps() == b'\x00\x00\x12\x34'


def test_loads__extraneous_data_crashes():
    field = binobj.Bytes(name='field', size=3)

    with pytest.raises(errors.ExtraneousDataError) as errinfo:
        field.loads(b'\xc0\xff\xee!')

    assert str(errinfo.value) == 'Expected to read 3 bytes, read 4.'


def test_loads__no_size_crashes():
    field = binobj.String()

    with pytest.raises(errors.UndefinedSizeError):
        field.loads(b'123')


NONDEFAULT_ENDIANNESS = 'big' if sys.byteorder == 'little' else 'little'


class StructWithFieldOverrides(binobj.Struct):
    one = binobj.UInt32(endian=NONDEFAULT_ENDIANNESS)
    two = binobj.Int32(endian=sys.byteorder)


def test_accessor__getitem():
    struct = StructWithFieldOverrides(one=1)

    assert 'one' in struct
    assert struct['one'] == 1
    assert struct.one == 1


def test_accessor__getitem__no_such_field():
    """Get a better error message if we try to get a field that doesn't exist."""
    struct = StructWithFieldOverrides()

    with pytest.raises(KeyError) as errinfo:
        struct['asdf'] = 1

    assert str(errinfo.value) == \
        '"Struct \'StructWithFieldOverrides\' has no field named \'asdf\'."'


class ComputedLengthStruct(binobj.Struct):
    """A struct whose length can be computed if values are defined."""
    int_value = binobj.UInt32()
    value = binobj.StringZ()

    @value.computes
    def _compute_value(self, all_fields):
        return str(all_fields['int_value'])


def test_computable_field_length():
    """Test getting the length of a variable-length struct that requires values
    to be set."""
    struct = ComputedLengthStruct(int_value=1234)
    assert len(struct) == 9


def test_accessor__setitem():
    struct = StructWithFieldOverrides(one=1)
    struct['two'] = 2

    assert struct.two == 2
    assert struct['two'] == 2


def test_accessor__setitem__no_such_field():
    """Crash if we try setting a field that doesn't exist."""
    struct = StructWithFieldOverrides(one=1)

    with pytest.raises(KeyError):
        struct['basdfdasf'] = 1


def test_accessor__delitem():
    struct = StructWithFieldOverrides(one=1)

    assert 'one' in struct
    del struct['one']
    assert 'one' not in struct


def test_accessor__delitem__no_such_field():
    """Crash if we try deleting a field that doesn't exist."""
    struct = StructWithFieldOverrides(one=1)

    with pytest.raises(KeyError):
        del struct['basdfdasf']


@pytest.mark.parametrize('instance', (
    StructWithFieldOverrides(),
    StructWithFieldOverrides(one=1),
    StructWithFieldOverrides(one=1, two=2),
))
def test_len__basic(instance):
    """Get the size of an instance with only fixed-length fields."""
    assert len(instance) == 8


class StringZTestStruct(binobj.Struct):
    header = binobj.UInt32()
    string = binobj.StringZ()
    trailer = binobj.UInt16()


def test_len__variable__assigned():
    """Get the size of an instance with a variable-length field that has a value
    assigned."""
    instance = StringZTestStruct(header=10, string='abc', trailer=11)
    assert len(instance) == 10


def test_len__variable__missing_some():
    """Get the size of an instance with a variable-length field, but doesn't
    have some constant-width values set."""
    instance = StringZTestStruct(string='abc')
    assert len(instance) == 10


def test_len__variable__missing_varlen():
    """Must crash if we're checking the length of a struct that doesn't have an
    assigned value to a variable-length field."""
    instance = StringZTestStruct()

    with pytest.raises(errors.MissingRequiredValueError) as errinfo:
        len(instance)

    assert errinfo.value.field is StringZTestStruct.string


def test_to_dict__all_defined():
    """Ensure to_dict() works if all fields are defined."""
    struct = StructWithFieldOverrides(one=1, two=2)
    expected = collections.OrderedDict((('one', 1), ('two', 2)))

    assert struct.to_dict() == expected
    assert dict(struct) == expected


def test_to_dict__no_fill():
    """to_dict() shouldn't fill undefined fields by default"""
    struct = StructWithFieldOverrides(two=2)
    expected = collections.OrderedDict(two=2)

    assert struct.to_dict() == expected
    assert dict(struct) == expected


class Basic(binobj.Struct):
    abc = binobj.Bytes(const=b'ABC')
    ghi = binobj.Int32()
    jkl = binobj.Int64(default=0xbadc0ffee)
    mno = binobj.String(size=2)


def test_to_dict__fill_no_default():
    """to_dict() shouldn't fill undefined fields by default"""
    struct = Basic(mno='?!')
    expected = collections.OrderedDict((
        ('abc', b'ABC'), ('ghi', binobj.UNDEFINED), ('jkl', 0xbadc0ffee),
        ('mno', '?!')))

    assert struct.to_dict(fill_missing=True) == expected
