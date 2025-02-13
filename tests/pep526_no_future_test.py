"""This file is supposed to be identical to pep526_test.py except without deferred type
annotations enabled by ``from __future__ import annotations``.

Once we drop support for Python <=3.10 this won't be necessary anymore.
"""

import random
from typing import Annotated
from typing import Any
from typing import ClassVar

import pytest

import binobj
from binobj import errors
from binobj import fields
from binobj.pep526 import dataclass


@pytest.fixture(
    params=[
        pytest.param(
            fields.String(size=16, encoding="ibm500"),
            id="instance_annotation",
        ),
        pytest.param(
            Annotated[str, fields.String(size=16, encoding="ibm500")],
            id="pep_593_annotation",
        ),
    ]
)
def BasicClass(request: Any) -> type[binobj.Struct]:
    basic_class = type(
        "BasicClass",
        (binobj.Struct,),
        {
            "__annotations__": {
                "some_value": fields.UInt16,
                "other_string": fields.StringZ,
                "string": request.param,
            },
            "other_string": "Default Value",
        },
    )

    return dataclass(basic_class)


def test_field_extraction__basic(BasicClass: type[binobj.Struct]):
    assert hasattr(BasicClass, "__annotations__")
    assert hasattr(BasicClass, "__binobj_struct__"), "Metadata not found on class"

    meta = BasicClass.__binobj_struct__
    assert meta.num_own_fields == 3, f"{meta.num_own_fields=}, wanted 3"
    assert meta.components, "No components found."
    assert set(meta.components.keys()) == {"some_value", "string", "other_string"}


def test_field_extraction__default_values(BasicClass: type[binobj.Struct]):
    assert BasicClass.other_string.default == "Default Value"


def test_field_extraction__field_properties_assigned(BasicClass: type[binobj.Struct]):
    assert BasicClass.string.encoding == "ibm500"


def test_field_redefine_detected_crashes__same_type(BasicClass: type[binobj.Struct]):
    """Redefining a field crashes, even if the field type is the same."""
    with pytest.raises(errors.FieldRedefinedError):

        @dataclass
        class _BrokenClass(BasicClass):
            other_string: fields.StringZ


def test_field_redefine_detected_crashes__different_type(
    BasicClass: type[binobj.Struct],
):
    """Redefining a field crashes (field type is different here)."""
    with pytest.raises(errors.FieldRedefinedError):

        @dataclass
        class _BrokenClass(BasicClass):
            other_string: fields.UInt16


def test_typing_union_breaks():
    """Attempting to use typing.Union for binobj.Union will break."""
    with pytest.raises(errors.InvalidTypeAnnotationError):

        @dataclass
        class _BrokenClass(binobj.Struct):
            some_value: binobj.UInt32 | binobj.UInt16


@dataclass
class NullableFieldsStruct(binobj.Struct):
    nullable: fields.Int32 | None
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


@pytest.fixture
def NestedFields(BasicClass: type[binobj.Struct]) -> type[binobj.Struct]:
    basic_class = type(
        "NestedFields",
        (binobj.Struct,),
        {
            "__annotations__": {
                "basic": BasicClass,
                "other": fields.Float32,
            }
        },
    )
    return dataclass(basic_class)


def test_nested_works(
    NestedFields: type[binobj.Struct], BasicClass: type[binobj.Struct]
):
    assert isinstance(NestedFields.basic, fields.Nested)
    assert NestedFields.basic.struct_class is BasicClass, (
        f"{NestedFields.basic.struct_class=}, wanted {BasicClass!r}"
    )


def test_passing_callable_triggers_warning():
    with pytest.deprecated_call():

        @dataclass
        class _DeprecatedCallable(binobj.Struct):
            some_field: fields.Int32 = lambda: random.randrange(1024)


@pytest.mark.xfail
def test_passing_callable_crashes():
    with pytest.raises(TypeError):

        @dataclass
        class _DeprecatedCallable(binobj.Struct):
            some_field: fields.Int32 = lambda: random.randrange(1024)


def test_pep593_annotated__basic():
    """Field declarations work as usual when using PEP-593 `typing.Annotated`."""

    @dataclass
    class PEP593Class(binobj.Struct):
        foo: Annotated[int, fields.UInt32] = 123
        bar: Annotated[int, fields.String(size=16)]
        ignore_me: int
        ignore_as_well: Annotated[int, bool]

    assert PEP593Class.__binobj_struct__.num_own_fields == 2
    validate_pep593_foo_bar_fields(PEP593Class)


def test_pep593_annotated__with_union():
    """Field declarations work as usual when using PEP-593 `typing.Annotated`.

    This test ensures that unions are correctly handled.
    """

    @dataclass
    class PEP593Class(binobj.Struct):
        foo: Annotated[int | float, fields.UInt32] = 123
        bar: Annotated[int | str | None, fields.String(size=16)]
        ignore_me: int
        ignore_as_well: Annotated[int, bool]

    assert PEP593Class.__binobj_struct__.num_own_fields == 2
    validate_pep593_foo_bar_fields(PEP593Class)


def test_pep593_annotated__not_as_first():
    """Field declarations work as usual when using PEP-593 `typing.Annotated`.

    This test ensures that we correctly handle the case wehre there are multiple non-
    BinObj declarations, and where the BinObj annotation isn't the first metadata.
    """

    @dataclass
    class PEP593Class(binobj.Struct):
        foo: Annotated[int, float, fields.UInt32, bool] = 123
        bar: Annotated[int | str, bool, fields.String(size=16)]
        ignore_me: int
        ignore_as_well: Annotated[int, bool]

    assert PEP593Class.__binobj_struct__.num_own_fields == 2
    validate_pep593_foo_bar_fields(PEP593Class)


def test_pep593_annotated__multiple_fields_crash__same_type():
    """Passing more than one BinObj annotation to a field detonates."""

    with pytest.raises(
        errors.ConfigurationError,
        match=r"^Field 'broken' of struct <class .+\.BrokenPEP593'> has 2 valid BinObj"
        r" annotations\. There must be at most one\.$",
    ):

        @dataclass
        class BrokenPEP593(binobj.Struct):
            okay: Annotated[int, float, fields.UInt32, bool]
            broken: Annotated[str, fields.String(size=16), fields.String(size=16)]
            ignore_me: int
            ignore_as_well: Annotated[int, bool]


def validate_pep593_foo_bar_fields(struct_class: type[binobj.Struct]) -> None:
    assert "foo" in struct_class.__binobj_struct__.components
    first_field = struct_class.__binobj_struct__.components["foo"]
    assert isinstance(first_field, fields.Field)
    assert first_field.name == "foo"
    assert first_field.index == 0
    assert first_field.offset == 0
    assert first_field.size == 4
    assert first_field.default == 123

    assert "bar" in struct_class.__binobj_struct__.components
    second_field = struct_class.__binobj_struct__.components["bar"]
    assert isinstance(second_field, fields.Field)
    assert second_field.name == "bar"
    assert second_field.index == 1
    assert second_field.offset == 4
    assert second_field.size == 16
