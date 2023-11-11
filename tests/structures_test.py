"""Tests for the structure objects."""

import io

import pytest

import binobj
from binobj import errors
from binobj import fields
from binobj.pep526 import dataclass


class BasicStruct(binobj.Struct):
    """A basic structure."""

    string = fields.String(size=7)
    int64 = fields.Int64(endian="big")
    uint24 = fields.UnsignedInteger(size=3, endian="little")


def test_getitem__basic():
    struct = BasicStruct(string="string!", int64=-1, uint24=123456)
    assert struct["int64"] == struct.int64


def test_getitem__no_such_field():
    struct = BasicStruct()
    with pytest.raises(KeyError):
        struct["asdfasdfasfsda"]


def test_eq_undefined():
    """A struct with entirely unassigned fields compares equal to UNDEFINED."""
    with pytest.deprecated_call():
        assert BasicStruct() == fields.UNDEFINED
    with pytest.deprecated_call():
        assert BasicStruct(int64=123) != fields.UNDEFINED


def test_eq_not_struct_or_mapping():
    """A struct with entirely unassigned fields compares equal to UNDEFINED."""
    assert BasicStruct() != "asduh48q3oth"
    assert BasicStruct(int64=123) != 123
    assert (
        BasicStruct(string="abcdefg", int64=0, uint24=0xC0FFEE)
        != b"abcdefg\0\0\0\0\0\0\0\0\xee\xff\xc0"
    )


def test_eq_struct_with_struct():
    """Structs should compare equal/not equal each other as expected"""
    assert BasicStruct() == BasicStruct()
    assert BasicStruct(int64=123) == BasicStruct(int64=123)

    assert BasicStruct(string="1234") != BasicStruct()
    assert BasicStruct(int64=123, string="") != BasicStruct(int64=123)
    assert BasicStruct(string="1234") != BasicStruct(string="0987")


def test_iter_skips_undefined_keys():
    assert list(BasicStruct()) == []
    assert list(BasicStruct(string="1234567")) == ["string"]


def test_basic__fields_loaded():
    """Ensure that the metaclass adds and marks fields properly."""
    assert hasattr(BasicStruct, "__binobj_struct__"), "Field dict missing."
    field_list = tuple(BasicStruct.__binobj_struct__.components.values())
    assert len(field_list) == 3

    assert field_list[0].name == "string"
    assert field_list[0].index == 0
    assert field_list[0].offset == 0

    assert field_list[1].name == "int64"
    assert field_list[1].index == 1
    assert field_list[1].offset == 7

    assert field_list[2].name == "uint24"
    assert field_list[2].index == 2
    assert field_list[2].offset == 15


def test_load__basic():
    stream = io.BytesIO(b"abcdefg\0\xba\xdc\x0f\xfe\xe1\x5b\xad\x01\x02\x03")
    struct = BasicStruct.from_stream(stream)

    assert struct.string == "abcdefg"
    assert struct.int64 == 0x00BADC0FFEE15BAD
    assert struct.uint24 == 0x030201


def test_load__short_read():
    """Crash if we don't have enough data to read all the fields."""
    stream = io.BytesIO(b"abcdefg\0\xba\xdc\x0f\xfe\xe1\x5b\xad\x01")

    with pytest.raises(errors.UnexpectedEOFError) as errinfo:
        BasicStruct.from_stream(stream)

    exc = errinfo.value
    assert exc.field is BasicStruct.uint24
    assert exc.offset == BasicStruct.uint24.offset
    assert exc.size == 3


def test_loads__extra_bytes():
    """Crash if we have too much data."""
    with pytest.raises(errors.ExtraneousDataError) as errinfo:
        BasicStruct.from_bytes(b"abcdefghijklmnopqrstuwxyz")

    exc = errinfo.value
    assert exc.offset == BasicStruct.uint24.offset + BasicStruct.uint24.size


def test_partial_load__bad_column():
    """Crash if an invalid column name is given."""
    stream = io.BytesIO(b"zyxwvut\0\xba\xdc\x0f\xfe\xe1\x5b\xad\x01")

    with pytest.raises(ValueError) as errinfo:
        BasicStruct.partial_load(stream, "lol")

    assert str(errinfo.value) == "BasicStruct doesn't have a field named 'lol'."


def test_partial_load__short_read():
    """A short read with no defined end field shouldn't crash partial_load()."""
    stream = io.BytesIO(b"zyxwvut\0\xba\xdc\x0f\xfe\xe1\x5b\xad\x01")

    # Make sure the correct data was loaded and that the last field was *not*
    # included in the output.
    output = BasicStruct.partial_load(stream)
    assert output["string"] == "zyxwvut"
    assert output["int64"] == 0x00BADC0FFEE15BAD

    # Stream head should've been repositioned properly as well.
    assert stream.tell() == BasicStruct.uint24.offset
    assert stream.read() == b"\x01"


def test_partial_load__stops():
    """Verify partial_load() stops at the right field."""
    stream = io.BytesIO(b"zyxwvut\0\xba\xdc\x0f\xfe\xe1\x5b\xad\x01\x02\x03extra data!")

    # int64 should be the last field included in the output.
    loaded = BasicStruct().partial_load(stream, "int64")
    assert loaded == BasicStruct(string="zyxwvut", int64=0x00BADC0FFEE15BAD)

    # Stream head should be at the beginning of the first unread field.
    assert stream.tell() == BasicStruct.uint24.offset
    assert stream.read() == b"\x01\x02\x03extra data!"


def test_partial_load__short_read_of_required():
    """Crash if we get a short read on a required field."""
    stream = io.BytesIO(b"zyxwvut\x0b\xad")

    # int64 should be the last field included in the output.
    with pytest.raises(errors.UnexpectedEOFError):
        BasicStruct.partial_load(stream, "int64")


def test_get_field__basic():
    """Retrieve a field."""
    stream = io.BytesIO(b"zyxwvut\0\xba\xdc\x0f\xfe\xe1\x5b\xad")

    assert BasicStruct.get_field(stream, "int64") == 0x00BADC0FFEE15BAD
    assert stream.tell() == 0, "Stream head was moved! :("

    assert BasicStruct.get_field(stream, "string") == "zyxwvut"
    assert stream.tell() == 0


def test_get_field__bad_name():
    with pytest.raises(ValueError) as errinfo:
        BasicStruct.get_field(None, ":)")

    assert str(errinfo.value) == "BasicStruct doesn't have a field named ':)'."


def test_dump__basic():
    """Verify basic dump works."""
    struct = BasicStruct(string="AbCdEfG", int64=-100, uint24=65535)
    output = struct.to_bytes()
    assert output == b"AbCdEfG\xff\xff\xff\xff\xff\xff\xff\x9c\xff\xff\0"


@pytest.mark.parametrize("extra_fields", [{"one"}, {"one", "two"}])
def test_dump__extra_fields(extra_fields):
    """Giving unrecognized fields will crash by default."""
    with pytest.raises(errors.UnexpectedValueError) as errinfo:
        BasicStruct(
            string="AbCdEfG", int64=-100, uint24=65535, **{k: 0 for k in extra_fields}
        )

    assert errinfo.value.names == extra_fields


def test_dump__missing_fields():
    """Crash if we're missing field a field without default values."""
    struct = BasicStruct(string="AbCdEfG", uint24=65535)

    with pytest.raises(errors.MissingRequiredValueError) as errinfo:
        struct.to_bytes()

    assert errinfo.value.field is BasicStruct.int64


class BasicStructWithDefaults(binobj.Struct):
    string = fields.String(size=7)
    int64 = fields.Int64(endian="big", default=0)
    uint24 = fields.UnsignedInteger(size=3, endian="little")


class VarlenStruct(binobj.Struct):
    n_items = fields.Int32()
    items = fields.Array(fields.Int32(), count=n_items)


class ConstArrayStruct(binobj.Struct):
    items = fields.Array(fields.Int32(), count=10)


class NestedConstArrayStruct(binobj.Struct):
    field_1 = fields.String(size=16)
    field_2 = fields.Array(fields.Nested(ConstArrayStruct), count=4)


def test_struct_size__basic():
    assert BasicStruct.get_size() == 18


def test_struct_size__varlen_returns_none():
    assert VarlenStruct.get_size() is None


def test_struct_size__fixed_array_ok():
    assert ConstArrayStruct.get_size() == 40


def test_struct_size__nested_ok():
    assert NestedConstArrayStruct.get_size() == 176


def test_partial_dump__full():
    """Test basic partial dump with all fields present or with defaults."""
    struct = BasicStructWithDefaults(string="AbCdEfG", uint24=65535)
    stream = io.BytesIO()

    struct.partial_dump(stream)
    assert stream.getvalue() == b"AbCdEfG\0\0\0\0\0\0\0\0\xff\xff\0"


def test_partial_dump__missing_last():
    """Ensure proper behavior if we're missing the last field."""
    struct = BasicStructWithDefaults(string="AbCdEfG")
    stream = io.BytesIO()

    struct.partial_dump(stream)
    assert stream.getvalue() == b"AbCdEfG\0\0\0\0\0\0\0\0"


def test_partial_dump__include_trailing_default():
    """Should still dump the last field if it's missing but has a default."""
    struct = BasicStructWithDefaults(string="AbCdEfG", uint24=65535)
    stream = io.BytesIO()

    struct.partial_dump(stream, "int64")
    assert stream.getvalue() == b"AbCdEfG\0\0\0\0\0\0\0\0"


def test_partial_dump__missing_values():
    struct = BasicStruct(string="AbCdEfG", uint24=65535)
    stream = io.BytesIO()

    with pytest.raises(errors.MissingRequiredValueError):
        struct.partial_dump(stream, "uint24")


class InheritedStruct(BasicStruct):
    """Extension of BasicStruct with additional fields."""

    other_string = fields.StringZ(encoding="utf-16-le")


def test_inheritance__basic_dump():
    """Ensure that inheritance works properly, i.e. the struct inherits all fields
    and then extends them."""
    struct = InheritedStruct(
        string=" " * 7, int64=0xDEADBEEF, uint24=0xFACE11, other_string="AbCd!"
    )
    assert (
        bytes(struct) == b"       \0\0\0\0\xde\xad\xbe\xef\x11\xce\xfa"
        b"A\0b\0C\0d\0!\0\0\0"
    )


def test_inheritance__multiple_struct_inheritance_crashes():
    """Crash if we try inheriting from multiple Struct classes."""

    with pytest.raises(errors.MultipleInheritanceError):

        class _Crash(BasicStruct, BasicStructWithDefaults):
            pass


def test_inheritance__field_redefinition_crashes():
    """Trying to redefine the"""
    with pytest.raises(errors.FieldRedefinedError):

        class _Crash(BasicStruct):
            string = fields.String(size=7)


def test_load__discarded_fields_not_present():
    class _Dumb(binobj.Struct):
        first = fields.String(size=2)
        reserved = fields.Bytes(const=b"\0\0", discard=True)
        last = fields.String(size=2)

    loaded = _Dumb().from_bytes(b"AB\0\0CD").to_dict()
    assert "reserved" not in loaded


class StructWithArgs(binobj.Struct):
    def __init__(self, required, **values):
        super().__init__(**values)
        self.required = required

    field_1 = fields.UInt16(endian="little")
    field_2 = fields.UInt32(endian="big")


def test_load__init_kwargs__basic():
    """Ensure passing extra arguments to a struct on initialization works."""
    struct = StructWithArgs.from_bytes(
        b"\x34\x12\xba\xdb\xee\xf1", init_kwargs={"required": 123}
    )

    # Ensure the additional argument we passed in is not considered in equality
    # comparisons.
    assert struct == {"field_1": 0x1234, "field_2": 0xBADBEEF1}
    assert struct.required == 123, "Additional argument value is wrong."


def test_load__init_kwargs__not_modified():
    """Ensure the dict of extra arguments passed to the struct isn't modified."""
    args = {"required": {"nested": "item"}}
    struct = StructWithArgs.from_bytes(b"\x34\x12\xba\xdb\xee\xf1", init_kwargs=args)

    assert struct.required == {"nested": "item"}
    assert args == {"required": {"nested": "item"}}, "Keyword arguments were modified!"
    assert struct.required is not args["required"], "Value was not deep copied!"


@pytest.mark.xfail(
    reason="Can't distinguish between empty assigned class and dataclass"
)
def test_no_fields_boom__really_has_no_fields__assignment():
    with pytest.raises(errors.NoDefinedFieldsError):

        class MyStruct(binobj.Struct):
            pass


@pytest.mark.xfail(
    reason="Can't distinguish between empty assigned class and dataclass"
)
def test_no_fields_boom__really_has_no_fields__dataclass():
    with pytest.raises(errors.NoDefinedFieldsError):

        @dataclass
        class MyStruct(binobj.Struct):
            pass
