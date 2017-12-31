"""Basic tests for serialization code."""

import pytest

from binobj.serialization import gather_options_for_class


class BaseClassWithOptions:
    class Options:
        foo = 'bar'
        bar = 'baz'
        _ignored = 'ignored'


class BaseClassWithoutOptions:
    pass


@pytest.mark.parametrize('class_object,expected', (
    (BaseClassWithOptions, {'foo': 'bar', 'bar': 'baz'}),
    (BaseClassWithoutOptions, {}),
))
def test_single_class(class_object, expected):
    """Basic test for single classes that have options."""
    assert gather_options_for_class(class_object) == expected
