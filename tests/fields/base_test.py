"""Tests for fields."""

import io
import re
import sys

import pytest

import binobj
from binobj import errors
from binobj import fields
from binobj.fields import DEFAULT


def test_load__null_with_null_value_basic():
    null_value = b" :( "
    field = fields.Bytes(name="field", size=4, null_value=null_value)
    assert field.allow_null is True
    assert field.from_stream(io.BytesIO(null_value)) is None


def test_load__null_with_default_null_value():
    field = fields.Bytes(name="field", size=4, null_value=DEFAULT)
    assert field.allow_null is True

    assert field.from_stream(io.BytesIO(b"\x00" * 4)) is None


def test_loads__field_insufficient_data():
    """Load a field when there's insufficient data -> BOOM"""
    with pytest.raises(errors.UnexpectedEOFError):
        fields.String(size=17).from_bytes(b"abc")


def test_dump_default():
    """Dump with only default value and no size should still be fine."""
    field = fields.Bytes(default=b"\0\0")
    assert field.to_bytes() == b"\0\0"


def test_const_sets_size__bytes():
    """Ensure passing `const` will set the size of a field if not given.

    In this case we assume the simple case where len(const) == size.
    """
    field = fields.Bytes(const=b"abcdef")
    assert field.size is not None, "Size wasn't set."
    assert field.size == 6, "Size is incorrect."


def test_default_doesnt_set_size__bytes():
    """Ensure passing `default` will NOT set the size of a field."""
    field = fields.Bytes(default=b"asdfghjk")
    assert field.size is None, "Size was set."


def test_const_set_size__string_ascii():
    """Passing `const` will set the size of a string correctly for single byte
    encodings.
    """
    field = fields.String(const="asdfghjkl")

    assert field.size is not None, "Size wasn't set."
    assert field.size == 9, "Size is incorrect."


def test_const_set_size__string_utf16():
    """Passing `const` will set the size of a string correctly for multi-byte
    encodings.
    """
    field = fields.String(const="asdf", encoding="utf-16-le")

    assert field.size is not None, "Size wasn't set."
    assert field.size == 8, "Size is incorrect."


def test_const_set_size__sized_int_works():
    """Already-sized integers shouldn't have a problem with the size override
    code.
    """
    field = fields.Int64(const=1234567890)
    assert field.size is not None, "Size wasn't set."
    assert field.size == 8, "Size is incorrect."


def test_const_set_size__stringz():
    """Variable-length strings MUST set their size with ``const``."""
    field = fields.StringZ(const="asdf")
    assert field.size is not None, "Size wasn't set."
    assert field.size == 5, "Size is incorrect."


def test_const_set_size__stringz_utf16():
    """Variable-length strings MUST set their size with ``const``."""
    field = fields.StringZ(const="wxyz", encoding="utf-16")
    assert field.size is not None, "Size wasn't set."
    assert field.size == 12, "Size is incorrect."


def test_dump__null_with_null_value():
    """Dumping None should use null_value"""
    field = fields.Bytes(name="field", size=4, null_value=b" :( ")
    assert field.allow_null is True
    assert field.to_bytes(None) == b" :( "


def test_dump__null_with_default_null():
    """No defined ``null_value`` --> dumps all null bytes."""
    field = fields.Bytes(name="field", size=4, null_value=DEFAULT)
    assert field.to_bytes(None) == b"\0\0\0\0"


def test_dump__null_with_default_and_varlen():
    """Crash if trying to write ``None`` when using the default null_value and
    field has no defined size."""
    field = fields.StringZ(name="field", null_value=DEFAULT)
    assert field.allow_null is True

    with pytest.raises(errors.UnserializableValueError):
        field.to_bytes(None)


@pytest.mark.parametrize("size_field", (fields.Int32(name="size"), "size"))
def test_dump__null_with_default_and_field_ref(size_field):
    """Successfully dump the expected number of nulls if the field is of variable length
    but has a defined size."""
    value_field = fields.String(name="string", size=size_field, null_value=DEFAULT)
    assert value_field.allow_null is True

    serialized_value = value_field.to_bytes(None, all_fields={"size": 5})
    assert serialized_value == b"\x00" * 5


def test_dump__no_null_value_crashes():
    """Crash if we try dumping None with no null_value set."""
    field = fields.Bytes(name="field", size=4)
    assert not field.allow_null

    with pytest.raises(errors.UnserializableValueError) as errinfo:
        field.to_bytes(None)

    assert errinfo.value.field is field
    assert errinfo.value.value is None


def test_dump__allow_null_correctly_set():
    """We still shouldn't be able to dump None if allow_null is false and
    null_value is provided."""
    field = fields.Bytes(name="field", size=4, null_value=b" :) ")
    assert field.allow_null is True

    field = fields.Bytes(name="field", size=4)
    assert field.allow_null is False


def test_dump__field_only__no_value_no_default():
    """Dumping a field with no predefined value crashes"""
    field = fields.Bytes(name="field", size=4)

    with pytest.raises(errors.MissingRequiredValueError):
        field.to_bytes()


class BasicStructWithArray(binobj.Struct):
    """A basic structure with a sized array."""

    header = fields.Bytes(const=b"ABC")
    numbers = fields.Array(fields.UInt16(endian="big"), count=2)
    trailer = fields.Bytes(const=b"XYZ")


def test_set_const_crashes__setattr():
    """Attempting to set a const field via attribute access crashes.

    Only use attribute access to avoid interaction with __setitem__.
    """
    with pytest.raises(
        errors.ImmutableFieldError,
        match=re.escape(
            "Cannot assign to immutable field: <binobj.fields.stringlike.Bytes("
            "name='header')"
        ),
    ):
        BasicStructWithArray().header = b"ABC"


def test_set_const_crashes__setitem():
    """Attempting to set a const field via dictionary access crashes.

    Only use dictionary access to avoid interaction with __set__.
    """
    with pytest.raises(
        errors.ImmutableFieldError,
        match=re.escape(
            "Cannot assign to immutable field: <binobj.fields.stringlike.Bytes("
            "name='header')>"
        ),
    ):
        BasicStructWithArray()["header"] = b"ABC"


def test_load__invalid_const():
    data = b"ASDFGHJXYZ"

    with pytest.raises(errors.ValidationError) as errinfo:
        BasicStructWithArray.from_bytes(data)

    assert errinfo.value.field is BasicStructWithArray.header
    assert errinfo.value.value == b"ASD"


class CircularReferenceComputedSize(binobj.Struct):
    """A struct with a size field and array that reference each other."""

    count = fields.UInt16(endian="big")
    stuff = fields.Array(fields.StringZ(), count=count)

    @count.computes
    def compute_count(self, all_fields):
        return len(all_fields["stuff"])


def test_set_computed_field__setattr():
    """Crash when trying to set a computed field via attribute access."""
    struct = CircularReferenceComputedSize()

    with pytest.raises(errors.ImmutableFieldError):
        struct.count = 123


def test_set_computed_field__setitem():
    """Crash when trying to set a computed field via attribute access."""
    struct = CircularReferenceComputedSize()

    with pytest.raises(errors.ImmutableFieldError):
        struct["count"] = 123


def test_circular_reference__load():
    """The array can load even though it relies on a computed field to determine
    its length."""
    loaded = CircularReferenceComputedSize.from_bytes(b"\x00\x03abc\x00\x00defg\x00")
    assert loaded.count == 3
    assert loaded.stuff == ["abc", "", "defg"]


def test_circular_reference__dump():
    """The array can dump even though it relies on a computed field that relies
    on it."""
    struct = CircularReferenceComputedSize(stuff=["a", "bc", "def", ""])
    assert struct.count == 4
    assert struct["count"] == 4
    assert struct.to_bytes() == b"\x00\x04a\0bc\0def\0\0"


def test_circular_reference__updates__getattr():
    """Ensure computed fields update when a value changes.

    We'll only use attribute access to avoid masking errors if __getitem__
    misbehaves.
    """
    struct = CircularReferenceComputedSize(stuff=["a", "bc", "def", ""])
    assert struct.count == 4

    struct.stuff = ["qwerty", "uiop"]
    assert struct.count == 2


def test_circular_reference__updates__getitem():
    """Ensure computed fields update when a value changes.

    We'll only use dictionary access to avoid masking errors if __get__
    misbehaves.
    """
    struct = CircularReferenceComputedSize(stuff=["a", "bc", "def", ""])
    assert struct["count"] == 4

    struct.stuff = ["qwerty", "uiop"]
    assert struct["count"] == 2


def test_descriptor_get():
    """A field should return itself when accessed from a class, and its assigned
    value when accessed from an instance."""
    assert isinstance(BasicStructWithArray.header, fields.Bytes)

    struct = BasicStructWithArray(header=b"abc")
    assert struct.header == b"abc"


def test_descriptor_set():
    """Setting a field on an instance should update values."""
    instance = BasicStructWithArray()

    assert "numbers" not in instance.__values__
    instance.numbers = [1, 2]
    assert "numbers" in instance.__values__, "Value was not set in instance"
    assert instance.__values__["numbers"] == [1, 2]


class BadField(fields.Field):
    """This field subclass doesn't override its required methods properly."""

    def _do_load(self, stream, context, loaded_fields):
        return super()._do_load(stream, context, loaded_fields)

    def _do_dump(self, stream, data, context, all_fields):
        return super()._do_dump(stream, data, context, all_fields)


def test_field_subclass_super_delegation():
    """Any delegation to super() by a Field subclass' load/dump functions must
    crash.
    """
    field = BadField()

    with pytest.raises(NotImplementedError):
        field.from_bytes(b" ")

    with pytest.raises(errors.UnserializableValueError):
        field.to_bytes(b" ")


class BasicPresentStruct(binobj.Struct):
    flags = fields.UInt16(endian="little")
    thing = fields.StringZ(present=lambda f, *_: f["flags"] & 0x8000)
    other_thing = fields.UInt16(const=0x1234, endian="little")

    @flags.computes
    def _flags(self, all_values):
        existing = all_values.get("flags", 0)
        if "thing" in all_values:
            return existing | 0x8000
        return existing


@pytest.mark.skipif(sys.version_info[:2] == (3, 5), reason="Test is flaky on 3.5.")
def test_present__load__not_present():
    data = b"\xff\x7f\x34\x12"
    struct = BasicPresentStruct.from_bytes(data)

    assert struct == {
        "flags": 0x7FFF,
        "thing": fields.NOT_PRESENT,
        "other_thing": 0x1234,
    }


@pytest.mark.skipif(sys.version_info[:2] == (3, 5), reason="Test is flaky on 3.5.")
def test_present__load__present():
    data = b"\xff\xffhello!\x00\x34\x12"
    struct = BasicPresentStruct.from_bytes(data)

    assert struct == {"flags": 0xFFFF, "thing": "hello!", "other_thing": 0x1234}


def test_present__dump__not_present_not_given():
    struct = BasicPresentStruct(flags=1, other_thing=0x1337)
    assert struct.to_bytes() == b"\x01\x00\x37\x13"


@pytest.mark.parametrize("thing", (fields.UNDEFINED, fields.NOT_PRESENT))
def test_present__dump_not_present_given_something(thing):
    """If a field whose presence is controlled by something else is ``UNDEFINED`` or
    ``NOT_PRESENT`` it shouldn't be dumped.
    """
    struct = BasicPresentStruct(flags=1, thing=thing, other_thing=0x1337)
    assert struct.to_bytes() == b"\x01\x00\x37\x13"


def test_binding_defaults_applied__basic():
    opposite_endian = "big" if sys.byteorder == "little" else "little"

    class Test(binobj.Struct):
        class Meta:
            argument_defaults = {"endian": opposite_endian}

        opposite = fields.Int32()
        unaffected = fields.Int32(endian=sys.byteorder)

    assert Test.opposite.endian == opposite_endian, "Default value wasn't applied"
    assert Test.unaffected.endian == sys.byteorder, "Explicit argument was overridden"


def test_binding_defaults_applied__class_name_prefix():
    opposite_endian = "big" if sys.byteorder == "little" else "little"

    class Test(binobj.Struct):
        class Meta:
            argument_defaults = {"Int16__endian": opposite_endian}

        opposite = fields.Int16()
        same_16 = fields.Int16(endian=sys.byteorder)
        unaffected = fields.Int32(endian=sys.byteorder)

    assert Test.opposite.endian == opposite_endian, "Default value wasn't applied"
    assert Test.same_16.endian == sys.byteorder, "Explicit argument was overridden"
    assert Test.unaffected.endian == sys.byteorder, "Explicit argument was overridden"


def test_callable_default_warns():
    """Passing a callable for `default` triggers a warning."""
    with pytest.deprecated_call():
        fields.Int32(name="whatever", default=lambda: 123)


def test_default_and_factory_triggers_error():
    with pytest.raises(
        errors.ConfigurationError,
        match="Do not pass values for both `default` and `factory`.",
    ):
        fields.Int8(name="asdf", default=123, factory=lambda: 123)


def test_explicit_name_mismatch_triggers_error():
    """Passing a name to a field that already had its name assigned by ``__set_name__``
    *and* it doesn't match triggers an error.
    """
    with pytest.raises(
        RuntimeError,
        match="Error calling __set_name__ on 'Bytes' instance 'asdf' in 'Broken'",
    ) as errinfo:

        class Broken(binobj.Struct):
            asdf = fields.Bytes(name="qwerty", size=10)

    cause = errinfo.value.__cause__
    assert isinstance(cause, errors.ConfigurationError)


def test_explicit_name_matches_no_error():
    """Passing a name to a field that already had its name assigned by ``__set_name__``
    but the names match will not trigger an error.
    """

    class ThisIsFine(binobj.Struct):
        asdf = fields.Bytes(name="asdf", size=10)

    assert ThisIsFine.asdf.name == "asdf"


def test_simulated_infinite_recursion():
    class BorkedField(fields.Field[int]):
        def _size_for_value(self, value):
            raise RecursionError

    borked = BorkedField(name="asdf", default=1)
    with pytest.raises(errors.BuggyFieldImplementationError):
        borked.get_expected_size({})
