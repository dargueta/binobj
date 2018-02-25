"""Basic tests for serialization code."""

import collections
import copy
import sys

import pytest

import binobj
from binobj import errors
from binobj.serialization import gather_options_for_class


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

    with pytest.raises(errors.VariableSizedFieldError):
        field.loads(b'123')


class BaseClassWithOptions(binobj.Struct):
    class Options:
        foo = 'bar'
        bar = 'baz'
        _ignored = 'ignored'


class BaseClassWithoutOptions(binobj.Struct):
    pass


class ChildClassNoOverrides(BaseClassWithOptions):
    pass


class ChildClassWithOptions(BaseClassWithOptions):
    class Options:
        child = True


class GrandchildWithOverrides(ChildClassWithOptions):
    class Options:
        foo = 123456


@pytest.mark.parametrize('class_object,expected', (
    (BaseClassWithOptions, {'foo': 'bar', 'bar': 'baz'}),
    (BaseClassWithoutOptions, {}),
))
def test_gather_options__single_class(class_object, expected):
    """Basic test for single classes that have options."""
    assert gather_options_for_class(class_object) == expected


def test_gather_options__inherits__no_additional_options():
    """A class with no options of its own inherits all options from its parent,
    so they should have identical results."""
    expected = gather_options_for_class(BaseClassWithOptions)
    assert gather_options_for_class(ChildClassNoOverrides) == expected


def test_gather_options__inherits__with_additional_options():
    """Verify a class defining its own options also inherits its parents'."""
    expected = {
        'foo': 'bar',
        'bar': 'baz',
        'child': True,
    }
    assert gather_options_for_class(ChildClassWithOptions) == expected


def test_gather_options__inherits__with_overrides():
    """Options set in child classes should override the parents' options."""
    expected = {
        'foo': 123456,
        'bar': 'baz',
        'child': True,
    }
    assert gather_options_for_class(GrandchildWithOverrides) == expected


NONDEFAULT_ENDIANNESS = 'big' if sys.byteorder == 'little' else 'little'


class StructWithFieldOverrides(binobj.Struct):
    class Options:
        endian = NONDEFAULT_ENDIANNESS

    one = binobj.UInt32()   # Should be non-default byte order.
    two = binobj.Int32(endian=sys.byteorder)


def test_gather_options__field_overrides_struct():
    """A field's options will override the defaults it inherited from its
    struct's options."""
    expected_one = {'endian': NONDEFAULT_ENDIANNESS, 'signed': False,
                    'const': binobj.UNDEFINED, 'default': binobj.UNDEFINED,
                    'discard': False}
    expected_two = {'endian': sys.byteorder, 'const': binobj.UNDEFINED,
                    'default': binobj.UNDEFINED, 'discard': False}

    assert StructWithFieldOverrides.one.__options__ == expected_one
    assert StructWithFieldOverrides.two.__options__ == expected_two
    assert StructWithFieldOverrides.one.endian == NONDEFAULT_ENDIANNESS
    assert StructWithFieldOverrides.two.endian == sys.byteorder


def test_accessor__getitem():
    struct = StructWithFieldOverrides(one=1)

    assert 'one' in struct
    assert struct['one'] == 1
    assert struct.one == 1


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

    with pytest.raises(errors.VariableSizedFieldError) as errinfo:
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
