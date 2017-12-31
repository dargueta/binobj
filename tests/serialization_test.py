"""Basic tests for serialization code."""

import pytest

from binobj.serialization import gather_options_for_class, _PREDEFINED_KWARGS


class BaseClassWithOptions:
    class Options:
        foo = 'bar'
        bar = 'baz'
        _ignored = 'ignored'


class BaseClassWithoutOptions:
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
    expected.update(_PREDEFINED_KWARGS)
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
    expected.update(_PREDEFINED_KWARGS)
    assert gather_options_for_class(ChildClassWithOptions) == expected


def test_gather_options__inherits__with_overrides():
    """Options set in child classes should override the parents' options."""
    expected = {
        'foo': 123456,
        'bar': 'baz',
        'child': True
    }
    expected.update(_PREDEFINED_KWARGS)
    assert gather_options_for_class(GrandchildWithOverrides) == expected
