"""Unit tests for some of the more complicated exception classes."""
from __future__ import annotations

import pytest

from binobj import errors


def test_configuration_error__no_args_crashes():
    with pytest.raises(ValueError, match=r"^At least one of `field`, .+$"):
        errors.ConfigurationError()


@pytest.mark.parametrize(
    ("field", "struct", "obj", "message"),
    [
        ("foo", None, None, "The field 'foo' was misconfigured."),
        (None, "bar", None, "The struct 'bar' was misconfigured."),
        (None, None, "baz", "The object 'baz' was misconfigured."),
        ("foo", "bar", None, "Field 'foo' in struct 'bar' was misconfigured."),
    ],
)
def test_configurationerror__default_messages(field, struct, obj, message):
    err = errors.ConfigurationError(field=field, struct=struct, obj=obj)
    assert str(err) == message


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ("blah", "1 unrecognized field(s) given to NoneType for serialization: 'blah'"),
        (
            ("asdf", "ghjkl"),
            "2 unrecognized field(s) given to NoneType for serialization: 'asdf',"
            " 'ghjkl'",
        ),
        (
            ("abc", "def", "abc"),
            "2 unrecognized field(s) given to NoneType for serialization: 'abc', 'def'",
        ),
    ],
)
def test_unexpectedvalueerror__field_list(fields, message):
    err = errors.UnexpectedValueError(name=fields, struct=None)
    assert message == str(err)
