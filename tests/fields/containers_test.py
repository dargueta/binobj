from __future__ import annotations

import io
import sys

import pytest

import binobj
from binobj import errors
from binobj import fields


class SubStruct(binobj.Struct):
    first = fields.UInt64(endian="big")
    second = fields.String(size=7)


class MainStruct(binobj.Struct):
    before = fields.Int16(endian="big")
    nested = fields.Nested(SubStruct)
    after = fields.Int8()


def test_nested__load_basic():
    loaded = MainStruct.from_bytes(
        b"\x01\x02\x76\x54\x32\x10\xfe\xdc\xba\x98String!\x7f"
    )

    assert loaded.before == 0x0102
    assert loaded.after == 0x7F
    assert loaded.nested.first == 0x76543210FEDCBA98
    assert loaded.nested.second == "String!"


def test_nested__dump_basic():
    data = MainStruct(before=0x0BAD, after=0x7F)
    # This differs from assigning the structure in the constructor. That feels like a
    # bug, but I have no idea why it's happening.
    data.nested = SubStruct(first=0x0FAD, second="HllWrld")
    assert bytes(data) == b"\x0b\xad\x00\x00\x00\x00\x00\x00\x0f\xadHllWrld\x7f"


@pytest.mark.parametrize(
    "data",
    [{"first": 0x0FAD, "second": "HllWrld"}, SubStruct(first=0x0FAD, second="HllWrld")],
)
def test_nested__dump_basic_dict_or_instance(data):
    """Test dumping both a dict and an instance"""
    data = MainStruct(before=0x0BAD, after=0x7F, nested=data)
    assert bytes(data) == b"\x0b\xad\x00\x00\x00\x00\x00\x00\x0f\xadHllWrld\x7f"


def test_array__basic():
    """Test deserializing a list of stuff."""
    sequence = fields.Array(fields.UInt8())
    result = sequence.from_bytes(b"\xde\xad\xbe\xef")
    assert result == [0xDE, 0xAD, 0xBE, 0xEF]


def test_array__sized__read():
    """Verify the behavior of a fixed-size array on loading."""
    sequence = fields.Array(fields.UInt8(), count=3)
    result = sequence.from_bytes(b"\xde\xad\xbe")
    assert result == [0xDE, 0xAD, 0xBE]


def test_array__sentinel():
    """Test deserializing a sequence that has a sentinel terminator."""

    def halt(_seq, _str, values, _context, _loaded_fields):
        return values and (values[-1] == 0xDEAD)

    sequence = fields.Array(fields.UInt16(endian="little"), halt_check=halt)

    result = sequence.from_bytes(b"\x00\x00\xff\x00\xad\xde\xff\xff", exact=False)
    assert result == [0, 0xFF, 0xDEAD]


@pytest.mark.skipif(sys.version_info[:2] == (3, 5), reason="Test is flaky on 3.5.")
def test_array__load_nested():
    """Try loading an array of structs."""
    field = fields.Array(fields.Nested(SubStruct), count=2)
    loaded = field.from_bytes(
        b"\xc0\xff\xee\xde\xad\xbe\xef\x00ABCDEFG"
        b"\xfa\xde\xdb\xed\xa5\x51\xed\x00HIJKLMN"
    )
    assert loaded == [
        {"first": 0xC0FFEEDEADBEEF00, "second": "ABCDEFG"},
        {"first": 0xFADEDBEDA551ED00, "second": "HIJKLMN"},
    ]


def test_array__dump_nested():
    """Try dumping an array of structs."""
    field = fields.Array(fields.Nested(SubStruct), count=2)
    dumped = field.to_bytes(
        [
            {"first": 0xC0FFEEDEADBEEF00, "second": "ABCDEFG"},
            {"first": 0xFADEDBEDA551ED00, "second": "HIJKLMN"},
        ]
    )

    assert (
        dumped == b"\xc0\xff\xee\xde\xad\xbe\xef\x00ABCDEFG"
        b"\xfa\xde\xdb\xed\xa5\x51\xed\x00HIJKLMN"
    )


class BasicStructWithArray(binobj.Struct):
    header = fields.String(const=True, default="ABC")
    numbers = fields.Array(fields.UInt16(endian="big"), count=2)
    trailer = fields.String(const=True, default="XYZ")


def test_array__fixed_in_struct():
    """Test a fixed array in a struct with elements surrounding it."""
    stream = io.BytesIO(b"ABC\xde\xad\xbe\xefXYZ")
    struct = BasicStructWithArray.from_stream(stream)

    assert struct.header == "ABC"
    assert struct.numbers == [0xDEAD, 0xBEEF]
    assert struct.trailer == "XYZ"


def bswsa_should_halt(_seq, _stream, values, _context, _loaded_fields):
    """Halting function for :attr:`BasicStructWithSentinelArray.numbers`."""
    if values and values[-1] == 0:
        # Hit sentinel, remove it from the end of the array.
        del values[-1]
        return True
    return False


class BasicStructWithSentinelArray(binobj.Struct):
    numbers = fields.Array(fields.UInt8(), halt_check=bswsa_should_halt)
    eof = fields.String(const=True, default="ABC")


def test_array__variable_length_sentinel_in_struct():
    stream = io.BytesIO(b"\x01\x02\x7f\x00ABC")
    loaded = BasicStructWithSentinelArray.from_stream(stream)

    assert loaded.numbers == [1, 2, 0x7F]
    assert loaded.eof == "ABC"


class BasicStructWithArraySizeField(binobj.Struct):
    n_numbers = fields.UInt8()
    numbers = fields.Array(fields.UInt8(), count=n_numbers)
    eof = fields.String(const=True, default="ABC")


class BasicStructWithArraySizeFieldAsName(binobj.Struct):
    n_numbers = fields.UInt8()
    numbers = fields.Array(fields.UInt8(), count="n_numbers")
    eof = fields.String(const=True, default="ABC")


@pytest.mark.parametrize(
    "cls", [BasicStructWithArraySizeField, BasicStructWithArraySizeFieldAsName]
)
def test_array__variable_length_size_in_struct(cls):
    stream = io.BytesIO(b"\x03\x01\x02\x7fABC")
    loaded = cls.from_stream(stream)

    assert loaded.numbers == [1, 2, 0x7F]
    assert loaded.eof == "ABC"


def test_array__variable_length_no_count_field_name_crashes():
    n_numbers = fields.UInt8()
    numbers_array = fields.Array(fields.UInt8(), count=n_numbers)
    with pytest.raises(errors.ConfigurationError):
        numbers_array.to_bytes([5, 6, 7, 8])


def test_array__variable_length_forward_reference_crashes():
    """A forward reference to a field must crash."""

    class _Crash(binobj.Struct):
        n_numbers = fields.UInt8()
        numbers = fields.Array(fields.UInt8(), count="eof")
        eof = fields.String(const=True, default="ABC")

    with pytest.raises(errors.FieldReferenceError):
        _Crash.from_bytes(b"\0\0ABC")


@pytest.mark.parametrize("count", [True, False, object()])
def test_array__bogus_count(count):
    with pytest.raises(TypeError):
        fields.Array(fields.UInt8(), count=count)


def test_array__dump_basic():
    struct = BasicStructWithSentinelArray(numbers=[1, 2, 3, 0])
    assert struct.to_bytes() == b"\x01\x02\x03\x00ABC"


@pytest.mark.parametrize(
    "iterable",
    [
        pytest.param(["abc", "123456"], id="sized"),
        pytest.param((s for s in ["abc", "123456"]), id="unsized"),
    ],
)
def test_array__sized_dump_ok(iterable):
    """Write a sized array with the expected number of values."""
    field = fields.Array(fields.StringZ(), count=2)
    assert field.to_bytes(iterable) == b"abc\x00123456\0"


def test_array__unsized_dump_ok():
    field = fields.Array(fields.StringZ())
    assert field.to_bytes(["abc", "123456"]) == b"abc\x00123456\0"


def test_array__sized_dump_too_big__unsized_iterable():
    """Crash if writing a generator with too many values."""
    field = fields.Array(fields.Int8(), count=2)
    with pytest.raises(errors.ArraySizeError) as err:
        field.to_bytes(x for x in range(10))

    assert err.value.n_expected == 2
    assert err.value.n_given == 3


def test_array__sized_dump_too_big__sized_iterable():
    """Crash if writing a sized iterable with too many values."""
    field = fields.Array(fields.Int8(), count=2)
    with pytest.raises(errors.ArraySizeError) as err:
        field.to_bytes({4, 8, 15, 16, 23, 42})

    assert err.value.n_expected == 2
    assert err.value.n_given == 6


def test_array__sized_dump_too_small__sized_iterable():
    """Crash if writing a sized iterable with too few values."""
    field = fields.Array(fields.Int32(), count=100)
    with pytest.raises(errors.ArraySizeError) as err:
        field.to_bytes((4, 8, 15, 16, 23, 42))

    assert err.value.n_expected == 100
    assert err.value.n_given == 6


def test_array__sized_dump_too_small__unsized_iterable():
    """Crash if writing a generator with too few values."""
    field = fields.Array(fields.Int32(), count=100)
    with pytest.raises(errors.ArraySizeError) as err:
        field.to_bytes(x for x in range(6))

    assert err.value.n_expected == 100
    assert err.value.n_given == 6


class StructWithComputedSizeArray(binobj.Struct):
    half_size = fields.UInt8()
    size = fields.UInt8()
    stuff = fields.Array(fields.UInt8(), count=size)

    @size.computes
    def compute_size(self, all_fields):
        return all_fields["half_size"] * 2


def test_array__computed_size():
    """The array should still work if the size is computed."""
    struct = StructWithComputedSizeArray(half_size=3, stuff=[1, 1, 2, 3, 5, 8])
    assert struct.size == 6
    assert bytes(struct) == b"\x03\x06\x01\x01\x02\x03\x05\x08"


def test_array__unbound_count_field():
    """An Array can't be passed an unbound Field for its `count` argument."""
    array = fields.Array(fields.Int8(), count=fields.Int8())
    with pytest.raises(errors.ConfigurationError):
        array.from_bytes(b"")


def test_array__count_wrong_type():
    """An Array can't be passed an unbound Field for its `count` argument."""
    array = fields.Array(fields.Int8())
    array.count = object()
    with pytest.raises(TypeError, match="Unexpected type for `count`: 'object'"):
        array.from_bytes(b"")


class UnionItemA(binobj.Struct):
    _id = fields.UInt8(const=True, default=0xFF)
    value = fields.StringZ()


class UnionItemB(binobj.Struct):
    _id = fields.UInt8(const=True, default=0x7F)
    other = fields.UInt16(endian="little")


def struct_load_decider(_stream, choices, _context, loaded_fields):
    data_type_id = loaded_fields["data_type"]
    return choices[data_type_id]


def struct_dump_decider(_data, choices, _context, all_fields):
    data_type_id = all_fields["data_type"]
    return choices[data_type_id]


class UnionContainer(binobj.Struct):
    data_type = fields.UInt8()
    item = fields.Union(
        UnionItemA,
        UnionItemB,
        load_decider=struct_load_decider,
        dump_decider=struct_dump_decider,
    )


@pytest.mark.parametrize(
    ("data_type", "item", "expected"),
    [
        pytest.param(0, {"value": "asdf"}, b"\0\xffasdf\0"),
        pytest.param(1, {"other": 0xAA55}, b"\x01\x7f\x55\xaa"),
        pytest.param(0, UnionItemA(value="asdf"), b"\0\xffasdf\0"),
    ],
)
def test_union__structs__dump_basic__dict(data_type, item, expected):
    """Basic test of dumping the Union field type."""
    struct = UnionContainer(data_type=data_type, item=item)
    assert struct.to_bytes() == expected


@pytest.mark.parametrize("item1", [{"other": 0xAA55}, UnionItemB(other=0xAA55)])
@pytest.mark.parametrize("item0", [{"value": "asdf"}, UnionItemA(value="asdf")])
def test_union__structs__dump_basic(item0, item1):
    """Basic test of dumping the Union field type."""
    struct = UnionContainer(data_type=0, item=item0)
    assert struct.to_bytes() == b"\0\xffasdf\0"

    struct = UnionContainer(data_type=1, item=item1)
    assert struct.to_bytes() == b"\x01\x7f\x55\xaa"


@pytest.mark.xfail
def test_union__structs__bad_data():
    # Because we convert structs to dicts before serializing, serialization crashes
    # early. `item` should be UnionItemA, deliberately passing the wrong one.
    struct = UnionContainer(data_type=0, item=UnionItemB(other=0x1234))
    with pytest.raises(errors.UnserializableValueError):
        struct.to_bytes()


def test_union__structs__load_basic():
    """Basic test of loading the Union field type."""
    struct = UnionContainer.from_bytes(b"\0\xffasdf\0")
    assert struct.to_dict() == {"data_type": 0, "item": {"_id": 0xFF, "value": "asdf"}}

    struct = UnionContainer.from_bytes(b"\x01\x7f\x55\xaa")
    assert struct.to_dict() == {"data_type": 1, "item": {"_id": 0x7F, "other": 0xAA55}}


def fields_load_decider(_stream, choices, _context, loaded_fields):
    data_type_id = loaded_fields["data_type"]
    return choices[data_type_id]


def fields_dump_decider(_data, choices, _context, all_fields):
    if isinstance(all_fields["item"], str):
        return choices[0]
    return choices[1]


class FieldsUnionContainer(binobj.Struct):
    data_type = fields.UInt8()
    item = fields.Union(
        fields.StringZ(),
        fields.UInt16(endian="little"),
        load_decider=fields_load_decider,
        dump_decider=fields_dump_decider,
    )


def test_union__fields__dump_basic():
    """Basic test of dumping the Union field type."""
    struct = FieldsUnionContainer(data_type=0, item="asdf")
    assert struct.to_bytes() == b"\0asdf\0"

    struct = FieldsUnionContainer(data_type=1, item=0xAA55)
    assert struct.to_bytes() == b"\x01\x55\xaa"


def test_union__fields__load_basic():
    """Basic test of loading the Union field type."""
    struct = FieldsUnionContainer.from_bytes(b"\0asdf\0")
    assert struct.to_dict() == {"data_type": 0, "item": "asdf"}

    struct = FieldsUnionContainer.from_bytes(b"\x01\x55\xaa")
    assert struct.to_dict() == {"data_type": 1, "item": 0xAA55}


def test_union__field_class_crashes():
    """Passing a Field class to a Union should crash."""
    with pytest.raises(
        errors.ConfigurationError,
        match=r"^A `Union` must be passed Field instances, not classes\.$",
    ):
        fields.Union(fields.StringZ, load_decider=None, dump_decider=None)


def test_union__dump_non_mapping_for_struct():
    """If the dump decider returns a Struct as the serializer,"""
    field = fields.Union(
        UnionContainer,
        fields.StringZ(),
        load_decider=None,
        dump_decider=(lambda _s, classes, _ctx, _fields: classes[0]),
    )

    with pytest.raises(
        TypeError, match="Cannot dump a non-Mapping-like object as a .+: 'foo'"
    ):
        field.to_bytes("foo")
