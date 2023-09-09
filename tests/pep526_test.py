"""Tests for declaring fields via PEP-526 variable annotations.

This file MUST be ignored by Python 3.5 tests. If not, importing it will trigger syntax
errors and you will be sad.
"""

import random
import typing
from typing import ClassVar
from typing import Optional

import pytest

import binobj
from binobj import errors
from binobj import fields
from binobj.pep526 import dataclass


@dataclass
class BasicClass(binobj.Struct):
    some_value: fields.UInt16
    string: fields.String(size=16, encoding="ibm500")  # noqa:F821
    other_string: fields.StringZ = "Default Value"


def test_field_extraction__basic():
    assert hasattr(BasicClass, "__annotations__")
    assert hasattr(BasicClass, "__binobj_struct__"), "Metadata not found on class"

    meta = BasicClass.__binobj_struct__
    assert meta.num_own_fields == 3, "Wrong number of fields detected"
    assert meta.components, "No components found."
    assert set(meta.components.keys()) == {"some_value", "string", "other_string"}


def test_field_extraction__default_values():
    assert BasicClass.other_string.default == "Default Value"


def test_field_extraction__field_properties_assigned():
    assert BasicClass.string.encoding == "ibm500"


@pytest.mark.parametrize("field_type", (fields.StringZ, fields.UInt16))
def test_field_redefine_detected_crashes(field_type):
    with pytest.raises(errors.FieldRedefinedError):

        @dataclass
        class _BrokenClass(BasicClass):
            other_string: field_type


def test_typing_union_breaks():
    """Attempting to use typing.Union for binobj.Union will break."""
    with pytest.raises(errors.InvalidTypeAnnotationError):

        @dataclass
        class _BrokenClass(binobj.Struct):
            some_value: typing.Union[binobj.UInt32, binobj.UInt16]


@dataclass
class NullableFieldsStruct(binobj.Struct):
    nullable: Optional[fields.Int32]
    not_nullable: fields.StringZ


def test_optional_resolved_correctly():
    assert NullableFieldsStruct.nullable.allow_null
    assert not NullableFieldsStruct.not_nullable.allow_null


@dataclass
class IgnoredFields(binobj.Struct):
    ignored: ClassVar[int] = 1234
    unmarked_ignored: int
    real_field: fields.StringZ


def test_unmarked_fields_ignored():
    assert hasattr(IgnoredFields, "__annotations__")
    assert hasattr(IgnoredFields, "__binobj_struct__"), "Metadata not found on class"

    meta = IgnoredFields.__binobj_struct__
    assert meta.num_own_fields == 1, "Wrong number of fields detected"


def test_mixed_declarations_crashes():
    with pytest.raises(errors.MixedDeclarationsError):

        @dataclass
        class _BrokenClass(binobj.Struct):
            normal_field = fields.UInt16()
            pep526_field: fields.StringZ


def test_decorator_with_only_assigned_fields_crashes():
    with pytest.raises(errors.MixedDeclarationsError):

        @dataclass
        class MyStruct(binobj.Struct):
            field = fields.Bytes(size=10)


@dataclass
class NestedFields(binobj.Struct):
    basic: BasicClass
    other: fields.Float32


def test_nested_works():
    assert isinstance(NestedFields.basic, fields.Nested)
    assert NestedFields.basic.struct_class is BasicClass


def test_passing_callable_triggers_warning():
    with pytest.deprecated_call():

        @dataclass
        class _DeprecatedCallable(binobj.Struct):
            some_field: fields.Int32 = lambda: random.randrange(1024)
