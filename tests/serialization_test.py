"""Basic tests for serialization code."""

import pytest

import binobj
from binobj.serialization import gather_options_for_class, _DEFAULT_OPTIONS


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
        'child': True
    }
    expected.update(_DEFAULT_OPTIONS)
    assert gather_options_for_class(ChildClassWithOptions) == expected


def test_gather_options__inherits__with_overrides():
    """Options set in child classes should override the parents' options."""
    expected = {
        'foo': 123456,
        'bar': 'baz',
        'child': True
    }
    expected.update(_DEFAULT_OPTIONS)
    assert gather_options_for_class(GrandchildWithOverrides) == expected


class ChildWithFields(binobj.Struct):
    class Options:
        blah = 123

    field = binobj.Int32(kw1=1, kw2=2)


def test_gather_options__field_inherits_struct():
    struct = ChildWithFields()

    assert 'blah' in struct.field.__options__
    assert struct.field.__options__['blah'] == 123
    assert struct.field.__options__['kw1'] == 1
    assert struct.field.__options__['kw2'] == 2


class StructWithFieldOverrides(binobj.Struct):
    class Options:
        endian = 'big'

    big = binobj.Int32()    # Should be big-endian
    little = binobj.Int32(endian='little')


def test_gather_options__field_overrides_struct():
    struct = StructWithFieldOverrides()
    expected_big = {'endian': 'big'}
    expected_little = {'endian': 'little'}

    expected_big.update(_DEFAULT_OPTIONS)
    expected_little.update(_DEFAULT_OPTIONS)

    assert struct.big.__options__ == expected_big
    assert struct.little.__options__ == expected_little
