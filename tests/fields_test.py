"""Tests for fields."""

# pylint: disable=invalid-name

import io

import pytest

from binobj import errors
from binobj import fields
from binobj import varints
from binobj import serialization
from binobj import structures


class DummyStruct(structures.Struct):
    """A struct that does nothing."""


def test_load__null_with_null_value():
    null_value = b' :( '
    field = fields.Bytes(name='field', size=4, null_value=null_value)
    field.struct_class = DummyStruct
    assert field.load(io.BytesIO(null_value)) is None


def test_dump__null_with_null_value():
    """Dumping None should use null_value"""
    field = fields.Bytes(name='field', size=4, null_value=b' :( ')
    field.struct_class = DummyStruct
    assert field.dumps(None) == b' :( '


def test_dump__null_with_default_null():
    """No defined ``null_value`` --> dumps all null bytes."""
    field = fields.Bytes(name='field', size=4, null_value=serialization.DEFAULT)
    field.struct_class = DummyStruct
    assert field.dumps(None) == b'\0\0\0\0'


def test_dump__null_with_no_def_and_varlen():
    """Crash if trying to write ``None`` when ``null_value`` is undefined and
    column is variable-length."""
    field = fields.VariableLengthInteger(name='field',
                                         encoding=varints.VarIntEncoding.ZIGZAG)
    field.struct_class = DummyStruct

    with pytest.raises(errors.UnserializableValueError):
        field.dumps(None)


def test_dump__allow_null_false_crashes():
    """Crash if we try dumping None and allow_null is False."""
    field = fields.Bytes(name='field', size=4, allow_null=False)
    field.struct_class = DummyStruct

    with pytest.raises(errors.UnserializableValueError) as errinfo:
        field.dumps(None)

    assert errinfo.value.field is field
    assert errinfo.value.value is None


def test_dump__allow_null_false_with_null_value_crashes():
    """We still shouldn't be able to dump None if allow_null is false and
    null_value is provided."""
    field = fields.Bytes(name='field', size=4, allow_null=False,
                         null_value=b' :) ')
    field.struct_class = DummyStruct

    with pytest.raises(errors.UnserializableValueError) as errinfo:
        field.dumps(None)

    assert errinfo.value.field is field
    assert errinfo.value.value is None
