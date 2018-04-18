"""Unit tests for the basic validators."""

import pytest

import binobj
from binobj import decorators
from binobj import errors
from binobj import fields


def alnum_validator(field, value):
    if not value.isalnum():
        raise errors.ValidationError('String is not alphanumeric.',
                                     field=field, value=value)


def test_validator__load_fails__one_func_passed():
    field = fields.String(size=5, validate=alnum_validator)

    with pytest.raises(errors.ValidationError):
        field.loads(b'ab!de')


def test_validator__dump_fails__one_func_passed():
    field = fields.String(size=5, validate=alnum_validator)

    with pytest.raises(errors.ValidationError):
        field.dumps('ab!de')


def test_validator__set_invalid_value_crashes():
    """Crash instantly if we try to set an invalid value on a struct."""
    class Class(binobj.Struct):
        text = fields.StringZ(validate=alnum_validator)

    struct = Class()

    with pytest.raises(errors.ValidationError):
        struct.text = '!'


def test_validator__init_invalid_value_doesnt_crash():
    """Don't crash if an invalid value is set for a field in the constructor."""
    class Class(binobj.Struct):
        text = fields.StringZ(validate=alnum_validator)

    struct = Class(text='!')
    with pytest.raises(errors.ValidationError):
        struct.to_bytes()


def test_validator_method__dump_crashes():
    """Decorated value validators crash properly on dumping."""
    class Class(binobj.Struct):
        text = fields.StringZ()

        @decorators.validates('text')
        def validate_text(self, field, value):
            alnum_validator(field, value)

    struct = Class(text='!')
    with pytest.raises(errors.ValidationError):
        struct.to_bytes()


def test_validator_method__load_crashes():
    """Decorated value validators crash properly on loading."""
    class Class(binobj.Struct):
        text = fields.StringZ()

        @decorators.validates('text')
        def validate_text(self, field, value):
            alnum_validator(field, value)

    with pytest.raises(errors.ValidationError):
        Class.from_bytes(b'!\0')


def test_validator__both_invoked():
    """If a field has validators on it, both it and a method validator must be
    invoked."""
    class Class(binobj.Struct):
        text = fields.StringZ(validate=alnum_validator)

        @decorators.validates('text')
        def validate_text(self, field, value):
            if len(value) % 2 != 0:
                raise errors.ValidationError(
                    'Invalid length.', field=field, value=value)

    # Must crash -- length is even, but string's not alphanumeric
    with pytest.raises(errors.ValidationError) as errinfo:
        Class(text='??').to_bytes()

    assert 'alphanumeric' in str(errinfo.value)

    # Must crash -- string's alphanumeric but the length is odd
    with pytest.raises(errors.ValidationError) as errinfo:
        Class(text='asd').to_bytes()

    assert 'length' in str(errinfo.value)

    # Must crash -- length is odd and string's not alphanumeric.
    with pytest.raises(errors.ValidationError):
        Class(text='crash?').to_bytes()