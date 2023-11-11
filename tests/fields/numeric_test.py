import datetime
import math
import struct
from unittest import mock

import pytest

from binobj import DEFAULT
from binobj import errors
from binobj import varints
from binobj.fields import numeric


def test_integer_overflow():
    """An overflow error should be rethrown as a serialization error."""
    field = numeric.UInt16()
    with pytest.raises(errors.UnserializableValueError):
        field.to_bytes(65536)


def test_integer_neg_with_positive():
    field = numeric.UInt32()
    with pytest.raises(errors.UnserializableValueError):
        field.to_bytes(-1)


def test_integer_no_specified_size():
    field = numeric.Integer()
    with pytest.raises(errors.UndefinedSizeError):
        field.from_bytes(b"abc")

    with pytest.raises(errors.UndefinedSizeError):
        field.to_bytes(123)


def test_const_set_size__varint():
    """Variable integers should set their size when ``const`` is defined."""
    field = numeric.VariableLengthInteger(
        vli_format=varints.VarIntEncoding.VLQ, const=987654321
    )
    assert field.size == 5


def test_varint__unsupported_encoding():
    """Crash if we try using an unsupported VarInt encoding."""
    with pytest.raises(errors.ConfigurationError) as errinfo:
        numeric.VariableLengthInteger(vli_format="uleb128")

    assert str(errinfo.value).startswith("Invalid or unsupported integer")


def test_varint__underflow():
    """Crash if VLQ gets a negative number."""
    field = numeric.VariableLengthInteger(vli_format=varints.VarIntEncoding.VLQ)
    with pytest.raises(errors.UnserializableValueError):
        field.to_bytes(-1)


@pytest.mark.parametrize(
    ("value", "expected"), [(127, b"\x7f"), (0x1234567890, b"\x82\xa3\xa2\xd9\xf1\x10")]
)
def test_varint__basic_dump(value, expected):
    """Test VLQ dump.

    We know that our codecs work (see varints_test.py) so here we're doing a
    perfunctory test to make sure dumping works as expected.
    """
    field = numeric.VariableLengthInteger(vli_format=varints.VarIntEncoding.VLQ)
    assert field.to_bytes(value) == expected


@pytest.mark.parametrize(("data", "expected"), [(b"\x3f", 0x3F)])
def test_varint__basic_load(data, expected):
    """Test VLQ load."""
    field = numeric.VariableLengthInteger(vli_format=varints.VarIntEncoding.VLQ)
    assert field.from_bytes(data) == expected


def test_varint__max_bytes():
    """Crash if a variable-length integer takes up too many bytes."""
    field = numeric.VariableLengthInteger(
        vli_format=varints.VarIntEncoding.VLQ, max_bytes=2
    )

    with pytest.raises(errors.ValueSizeError):
        field.to_bytes(100000)


@pytest.mark.parametrize(
    ("null_value", "serialized"), [(-1, b"\x7f"), (b"\x7f\xff", b"\x7f\xff")]
)
def test_varint__dump_null_value(null_value, serialized):
    field = numeric.VariableLengthInteger(
        vli_format=varints.VarIntEncoding.LEB128, max_bytes=2, null_value=null_value
    )
    assert field.to_bytes(None) == serialized


@pytest.mark.parametrize(
    ("null_value", "serialized"), [(-1, b"\x7f"), (b"\x7f\xff", b"\x7f\xff")]
)
def test_varint__load_null_value(null_value, serialized):
    field = numeric.VariableLengthInteger(
        vli_format=varints.VarIntEncoding.LEB128, max_bytes=2, null_value=null_value
    )
    assert field.from_bytes(serialized) is None


def test_varint__dump_default_null():
    field = numeric.VariableLengthInteger(
        vli_format=varints.VarIntEncoding.ULEB128,
        max_bytes=2,
        null_value=0x7F,
        default=None,
    )
    assert field.to_bytes(None) == b"\x7f"


def test_varint__dump_factory_null():
    field = numeric.VariableLengthInteger(
        vli_format=varints.VarIntEncoding.ULEB128,
        max_bytes=2,
        null_value=0x7F,
        factory=lambda: None,
    )
    assert field.to_bytes(None) == b"\x7f"


def test_varint__load_null_value_default_warns():
    """Passing DEFAULT for `null_value` will break variable length integers since
    we can't guess what the falsy value for the datatype is (if that even exists).
    """
    field = numeric.VariableLengthInteger(
        vli_format=varints.VarIntEncoding.LEB128, max_bytes=2, null_value=DEFAULT
    )
    with pytest.raises(errors.CannotDetermineNullError):
        assert field.from_bytes(b"\x1f") == 31


def test_varint__dump_null_value_default_crashes():
    """Passing DEFAULT for `null_value` will always break variable length integers since
    we can't guess what the falsy value for the datatype is (if that even exists).
    """
    field = numeric.VariableLengthInteger(
        vli_format=varints.VarIntEncoding.LEB128, max_bytes=2, null_value=DEFAULT
    )
    with pytest.raises(errors.UnserializableValueError):
        field.to_bytes(None)


def test_float_bad_endian_crashes():
    """Endianness must be either 'little' or 'big'."""
    with pytest.raises(errors.ConfigurationError):
        numeric.Float64(endian="broken")


@pytest.mark.parametrize(
    ("field_object", "fmt_string"),
    [
        (numeric.Float32(endian="little"), "<f"),
        (numeric.Float64(endian="little"), "<d"),
        (numeric.Float32(endian="big"), ">f"),
        (numeric.Float64(endian="big"), ">d"),
    ],
)
@pytest.mark.parametrize("value", [math.pi, math.inf, -math.inf, math.nan])
def test_float__dumps(value, field_object, fmt_string):
    assert field_object.to_bytes(value) == struct.pack(fmt_string, value)


@pytest.mark.parametrize(
    ("field_object", "fmt_string"),
    [
        (numeric.Float32(endian="little"), "<f"),
        (numeric.Float64(endian="little"), "<d"),
        (numeric.Float32(endian="big"), ">f"),
        (numeric.Float64(endian="big"), ">d"),
    ],
)
@pytest.mark.parametrize("value", [math.pi, math.inf, -math.inf])
def test_float__loads(value, field_object, fmt_string):
    assert field_object.from_bytes(struct.pack(fmt_string, value)) == pytest.approx(
        value
    )


def test_float16__loads():
    field = numeric.Float16(endian="little")
    result = field.from_bytes(struct.pack("<e", math.e))
    assert math.isclose(result, math.e, rel_tol=0.001)


def test_float16__dumps():
    field = numeric.Float16(endian="big")
    assert field.to_bytes(65504) == struct.pack(">e", 65504)


@mock.patch("binobj.fields.numeric.struct.unpack")
def test_float__loads__exception_translation(pack_mock):
    """:class:`struct.error` must be translated."""
    pack_mock.side_effect = struct.error("Some error happened")

    with pytest.raises(errors.DeserializationError):
        numeric.Float32().from_bytes(b"1234")


@mock.patch("binobj.fields.numeric.struct.pack")
def test_float__dumps__exception_translation(pack_mock):
    """:class:`struct.error` must be translated."""
    pack_mock.side_effect = struct.error("Some error happened")

    with pytest.raises(errors.SerializationError):
        numeric.Float32().to_bytes(1234)


def test_timestamp__invalid_resolution():
    with pytest.raises(errors.ConfigurationError):
        numeric.Timestamp(size=4, resolution="Y")


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (
            b"\0\0\0\x80",
            datetime.datetime(1901, 12, 13, 20, 45, 52, tzinfo=datetime.timezone.utc),
        ),
        (
            b"\xff\xff\xff\x7f",
            datetime.datetime(2038, 1, 19, 3, 14, 7, tzinfo=datetime.timezone.utc),
        ),
    ],
)
def test_timestamp__loads__naive(data, expected):
    field = numeric.Timestamp32(endian="little", tz_aware=True)
    assert field.from_bytes(data) == expected


def test_timestamp__loads__aware():
    field = numeric.Timestamp32(endian="little", tz_aware=True)
    loaded = field.from_bytes(b"\x01\x23\x45\x67")
    assert loaded == datetime.datetime(
        2024, 11, 26, 1, 23, 13, tzinfo=datetime.timezone.utc
    )


def test_timestamp__loads__microseconds():
    field = numeric.Timestamp64(endian="big", resolution="us", tz_aware=True)
    loaded = field.from_bytes(b"\x00\x05\x81\x85\x84\x32\xc1\xad")
    assert loaded == datetime.datetime(
        2019, 2, 10, 7, 55, 32, 105645, datetime.timezone.utc
    )


def test_timestamp__roundtrip():
    field = numeric.Timestamp(size=12, resolution="us", tz_aware=True)
    now = datetime.datetime.now(datetime.timezone.utc)
    assert field.from_bytes(field.to_bytes(now)) == now


def test_timestamp__aware_cast_to_utc():
    """Timezone-aware datetimes must be cast to UTC before dumping."""
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    est_tz = datetime.timezone(datetime.timedelta(hours=-5))
    now_est = now_utc.astimezone(est_tz)

    field = numeric.Timestamp64(endian="little", resolution="us", tz_aware=True)
    assert field.to_bytes(now_est) == field.to_bytes(now_utc)
    assert field.from_bytes(field.to_bytes(now_est)) == now_utc


def test_timestamp__naive_assumes_local():
    """Naive datetimes are assumed to be local when dumping, and are loaded as UTC."""
    utc = datetime.datetime.now(datetime.timezone.utc)
    local_aware = utc.astimezone()
    local_naive = local_aware.replace(tzinfo=None)

    field = numeric.Timestamp64(endian="little", resolution="us", tz_aware=True)
    with pytest.deprecated_call():
        assert field.to_bytes(utc) == field.to_bytes(local_naive)
    assert field.from_bytes(field.to_bytes(local_naive)) == local_aware


def test_timestamp__warn_writing_aware_to_naive():
    """Warn when writing an aware timestamp to a naive field.."""
    utc = datetime.datetime.now(datetime.timezone.utc)
    local_naive = utc.astimezone().replace(tzinfo=None)

    field = numeric.Timestamp64(endian="little", resolution="us", tz_aware=False)
    with pytest.deprecated_call():
        assert field.to_bytes(utc) == field.to_bytes(local_naive)
    assert field.from_bytes(field.to_bytes(local_naive)) == local_naive


def test_timestamp__naive_round_trip_truncated():
    now = datetime.datetime.now()
    now_rounded = now.replace(microsecond=0)
    field = numeric.Timestamp64(endian="little", resolution="s")
    assert field.from_bytes(field.to_bytes(now)) == now_rounded


def test_timestamp__aware_round_trip_truncated():
    now = datetime.datetime.now(datetime.timezone.utc)
    now_rounded = now.replace(microsecond=0)
    field = numeric.Timestamp64(endian="little", resolution="s", tz_aware=True)
    assert field.from_bytes(field.to_bytes(now)) == now_rounded


@pytest.mark.parametrize("tz", [None, datetime.timezone.utc])
def test_2038_problem_caught__dumping(tz):
    """32-bit signed timestamps crash if we try serializing a date past the Epochalypse.

    https://en.wikipedia.org/wiki/Year_2038_problem
    """
    field = numeric.Timestamp32(resolution="s", tz_aware=tz is not None)
    with pytest.raises(errors.UnserializableValueError):
        field.to_bytes(datetime.datetime(2038, 1, 20, tzinfo=tz))
