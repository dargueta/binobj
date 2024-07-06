"""Basic tests for serialization code."""

import collections
import copy
import sys

import pytest

import binobj
from binobj import errors
from binobj import fields
from binobj import varints


def test_sentinels_are_singletons():
    """Verify deep copying works on sentinels.

    Deep copying, at least on some versions of Python, is implemented via
    pickling and then unpickling the container. If the sentinel class isn't
    implemented properly, we could end up with two sentinel objects that map to
    ``UNDEFINED`` or ``DEFAULT``.
    """
    dct = {"key": binobj.UNDEFINED}
    copied_dict = copy.deepcopy(dct)
    assert copied_dict["key"] is binobj.UNDEFINED


def test_dump__unserializable():
    field = fields.Int32(name="field")
    garbage = 2**32

    with pytest.raises(errors.UnserializableValueError) as errinfo:
        field.to_bytes(garbage)

    assert "can't serialize value" in str(errinfo.value)
    assert errinfo.value.field is field
    assert errinfo.value.value == garbage


def test_dump__use_default_value():
    """Test dumping when the default value is a constant."""
    field = fields.UInt32(name="field", default=0xDEADBEEF, endian="big")
    assert field.to_bytes() == b"\xde\xad\xbe\xef"


def test_dump__use_default_callable_warns():
    """Test dumping when the default value is a callable."""
    with pytest.deprecated_call():
        fields.UInt32(name="field", default=lambda: 0x1234, endian="big")


@pytest.mark.xfail
def test_dump__use_default_callable_crashes():
    """Test dumping when the default value is a callable."""
    with pytest.raises(TypeError):
        fields.UInt32(name="field", default=lambda: 0x1234, endian="big")


def test_loads__extraneous_data_crashes():
    field = fields.Bytes(name="field", size=3)

    with pytest.raises(errors.ExtraneousDataError) as errinfo:
        field.from_bytes(b"\xc0\xff\xee!")

    assert str(errinfo.value) == "Expected to read 3 bytes, read 4."


def test_loads__no_size_crashes():
    field = fields.String()

    with pytest.raises(errors.UndefinedSizeError):
        field.from_bytes(b"123")


NONDEFAULT_ENDIANNESS = "big" if sys.byteorder == "little" else "little"


class StructWithFieldOverrides(binobj.Struct):
    one = fields.UInt32(endian=NONDEFAULT_ENDIANNESS)
    two = fields.Int32(endian=sys.byteorder)


def test_accessor__getitem():
    struct = StructWithFieldOverrides(one=1)

    assert "one" in struct
    assert struct["one"] == 1
    assert struct.one == 1


def test_accessor__getitem__no_such_field():
    """Get a better error message if we try to get a field that doesn't exist."""
    struct = StructWithFieldOverrides()

    with pytest.raises(KeyError) as errinfo:
        struct["asdf"] = 1

    assert (
        str(errinfo.value)
        == "\"Struct 'StructWithFieldOverrides' has no field named 'asdf'.\""
    )


class ComputedLengthStruct(binobj.Struct):
    """A struct whose length can be computed if values are defined."""

    int_value = fields.UInt32()
    value = fields.StringZ()

    @value.computes
    def _compute_value(self, all_fields):
        return str(all_fields["int_value"])


def test_computable_field_length():
    """Test getting the length of a variable-length struct that requires values
    to be set."""
    struct = ComputedLengthStruct(int_value=1234)
    assert len(struct) == 9


def test_accessor__setitem():
    struct = StructWithFieldOverrides(one=1)
    struct["two"] = 2

    assert struct.two == 2
    assert struct["two"] == 2


def test_accessor__setitem__no_such_field():
    """Crash if we try setting a field that doesn't exist."""
    struct = StructWithFieldOverrides(one=1)

    with pytest.raises(KeyError):
        struct["basdfdasf"] = 1


def test_accessor__delitem():
    struct = StructWithFieldOverrides(one=1)

    assert "one" in struct
    del struct["one"]
    assert "one" not in struct


def test_accessor__delitem__no_such_field():
    """Crash if we try deleting a field that doesn't exist."""
    struct = StructWithFieldOverrides(one=1)

    with pytest.raises(KeyError):
        del struct["basdfdasf"]


@pytest.mark.parametrize(
    "instance",
    [
        StructWithFieldOverrides(),
        StructWithFieldOverrides(one=1),
        StructWithFieldOverrides(one=1, two=2),
    ],
)
def test_len__basic(instance):
    """Get the size of an instance with only fixed-length fields."""
    assert len(instance) == 8


class StringZTestStruct(binobj.Struct):
    header = fields.UInt32()
    string = fields.StringZ()
    trailer = fields.UInt16()


def test_len__variable__assigned():
    """Get the size of an instance with a variable-length field that has a value
    assigned."""
    instance = StringZTestStruct(header=10, string="abc", trailer=11)
    assert len(instance) == 10


def test_len__variable__missing_some():
    """Get the size of an instance with a variable-length field, but doesn't
    have some constant-width values set."""
    instance = StringZTestStruct(string="abc")
    assert len(instance) == 10


def test_len__variable__missing_varlen():
    """Must crash if we're checking the length of a struct that doesn't have an
    assigned value to a variable-length field."""
    instance = StringZTestStruct()

    with pytest.raises(errors.MissingRequiredValueError) as errinfo:
        len(instance)

    assert errinfo.value.field is StringZTestStruct.string


def test_to_dict__all_defined():
    """Ensure to_dict() works if all fields are defined."""
    struct = StructWithFieldOverrides(one=1, two=2)
    expected = collections.OrderedDict((("one", 1), ("two", 2)))

    assert struct.to_dict() == expected


def test_to_dict__crash_on_undefined():
    """to_dict() must crash if a field is undefined."""
    struct = StructWithFieldOverrides(two=2)
    with pytest.raises(errors.MissingRequiredValueError) as errinfo:
        struct.to_dict()

    assert errinfo.value.field is StructWithFieldOverrides.one


class Basic(binobj.Struct):
    abc = fields.Bytes(const=b"ABC")
    ghi = fields.Int32()
    jkl = fields.Int64(default=0xBADC0FFEE)
    mno = fields.String(size=2)


class VLenBytes(binobj.Struct):
    length = fields.VariableLengthInteger(vli_format=varints.VarIntEncoding.VLQ)
    data = fields.Bytes()

    @length.computes
    def _compute_length(self, all_fields):
        return len(all_fields["data"])


def test_vli_write_size__dumps():
    """Test what happens when the write size is a VLI"""
    struct = VLenBytes(data=b"asdfghjkl;")
    assert struct.to_bytes() == b"\x0aasdfghjkl;"
