"""Basic tests for serialization code."""

import sys

import pytest

import binobj
from binobj import errors
from binobj.serialization import _DEFAULT_OPTIONS
from binobj.serialization import gather_options_for_class


def test_dump__unserializable():
    field = binobj.Bytes(name='field', size=4)
    garbage = object()

    with pytest.raises(errors.UnserializableValueError) as errinfo:
        field.dumps(garbage)

    assert 'Unhandled data type: object' in str(errinfo.value)
    assert errinfo.value.field is field
    assert errinfo.value.value is garbage


def test_dump__use_default():
    field = binobj.UInt32(name='field', default=0xdeadbeef, endian='big')
    assert field.dumps() == b'\xde\xad\xbe\xef'


def test_loads__extraneous_data_crashes():
    field = binobj.Bytes(name='field', size=3)

    with pytest.raises(errors.ExtraneousDataError) as errinfo:
        field.loads(b'\xc0\xff\xee!')

    assert str(errinfo.value) == 'Expected to read 3 bytes, read 4.'


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
    expected.update(_DEFAULT_OPTIONS)
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
    expected.update(_DEFAULT_OPTIONS)
    assert gather_options_for_class(ChildClassWithOptions) == expected


def test_gather_options__inherits__with_overrides():
    """Options set in child classes should override the parents' options."""
    expected = {
        'foo': 123456,
        'bar': 'baz',
        'child': True,
    }
    expected.update(_DEFAULT_OPTIONS)
    assert gather_options_for_class(GrandchildWithOverrides) == expected


class ChildWithFields(binobj.Struct):
    class Options:
        blah = 123

    field = binobj.Int32(kw1=1, kw2=2)


def test_gather_options__field_inherits_struct():
    assert 'blah' in ChildWithFields.field.__options__
    assert ChildWithFields.field.__options__['blah'] == 123
    assert ChildWithFields.field.__options__['kw1'] == 1
    assert ChildWithFields.field.__options__['kw2'] == 2


NONDEFAULT_ENDIANNESS = 'big' if sys.byteorder == 'little' else 'little'


class StructWithFieldOverrides(binobj.Struct):
    class Options:
        endian = NONDEFAULT_ENDIANNESS

    one = binobj.UInt32()   # Should be non-default byte order.
    two = binobj.Int32(endian=sys.byteorder)


def test_gather_options__field_overrides_struct():
    """A field's options will override the defaults it inherited from its
    struct's options."""
    expected_one = {'endian': NONDEFAULT_ENDIANNESS, 'signed': False}
    expected_two = {'endian': sys.byteorder}    # `signed` = `True` implied

    expected_one.update(_DEFAULT_OPTIONS)
    expected_two.update(_DEFAULT_OPTIONS)

    assert StructWithFieldOverrides.one.__options__ == expected_one
    assert StructWithFieldOverrides.two.__options__ == expected_two
    assert StructWithFieldOverrides.one.endian == NONDEFAULT_ENDIANNESS
    assert StructWithFieldOverrides.two.endian == sys.byteorder
