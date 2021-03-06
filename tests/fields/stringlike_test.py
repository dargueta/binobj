import sys

import pytest

from binobj import DEFAULT
from binobj import errors
from binobj import fields
from binobj.fields import stringlike


def test_bytes__dump_too_short():
    """Crash if we try dumping a Bytes field without enough bytes."""
    field = stringlike.Bytes(size=4)

    with pytest.raises(errors.ValueSizeError):
        field.to_bytes(b"")


def test_bytes__dump_too_long():
    """Crash if we try dumping a Bytes field too many bytes."""
    field = stringlike.Bytes(size=4)

    with pytest.raises(errors.ValueSizeError):
        field.to_bytes(b"!" * 11)


def test_bytes__null():
    field = fields.Bytes(size=7, null_value=DEFAULT)
    assert field.to_bytes(None) == b"\x00" * 7


def test_string__load_basic():
    """Basic test of loading a String"""
    field = stringlike.String(size=13, encoding="utf-8")
    assert field.from_bytes(b"\xc2\xaf\\_(\xe3\x83\x84)_/\xc2\xaf") == r"¯\_(ツ)_/¯"


def test_string__dump_basic():
    """Basic test of dumping a String"""
    field = stringlike.String(size=13, encoding="utf-8")
    assert field.to_bytes(r"¯\_(ツ)_/¯") == b"\xc2\xaf\\_(\xe3\x83\x84)_/\xc2\xaf"


def test_string__dump_no_size():
    """Try dumping a string without its size set."""
    field = stringlike.String()
    with pytest.raises(errors.UndefinedSizeError):
        field.to_bytes("asdf")


@pytest.mark.parametrize("size_field", (fields.UInt8(name="size"), "size"))
def test_string__dump_variable_size(size_field):
    """Dumping a field with variable size should work."""
    field = stringlike.String(size=size_field)
    assert field.to_bytes("asdf", all_fields={"size": 4}) == b"asdf"


def test_string__dump_too_long_before_encoding():
    """Basic test of dumping a string that's too long into a String."""
    field = stringlike.String(size=5, encoding="utf-8")
    with pytest.raises(errors.ValueSizeError):
        assert field.to_bytes("abcdefg")


def test_string__dump_too_long_after_encoding():
    """Test dumping a string that's too long only after encoding to bytes."""
    field = stringlike.String(size=4, encoding="utf-8")
    with pytest.raises(errors.ValueSizeError):
        assert field.to_bytes("très")


def test_string__dump_too_short_before_encoding():
    """Basic test of dumping a string that's too short into a String."""
    field = stringlike.String(size=5, encoding="utf-8")
    with pytest.raises(errors.ValueSizeError):
        assert field.to_bytes("a")


def test_string__dump_too_short_before_encoding__pad():
    """Dumping a string that's too short before encoding is okay."""
    field = stringlike.String(size=5, pad_byte=b" ")
    assert field.to_bytes("a") == b"a    "


def test_string__dump_too_short_after_encoding__pad():
    """Dumping a string that's too short but uses padding is okay."""
    field = stringlike.String(size=8, pad_byte=b"\0", encoding="utf-32-be")
    assert field.to_bytes("a") == b"\0\0\0a\0\0\0\0"


def test_string__dump_too_long_before_encoding__pad():
    """``pad_byte`` shouldn't prevent a crash if a string is too long."""
    field = stringlike.String(size=5, pad_byte=b"?")
    with pytest.raises(errors.ValueSizeError):
        field.to_bytes("abcdefgh")


def test_string__dump_too_long_after_encoding__pad():
    """``pad_byte`` shouldn't prevent a crash if a string is too long after
    encoding it."""
    field = stringlike.String(size=3, pad_byte=b"?", encoding="utf-16-le")
    with pytest.raises(errors.ValueSizeError):
        field.to_bytes("ab")


def test_string__dump_null_default():
    field = fields.String(size=7, null_value=DEFAULT)
    assert field.to_bytes(None) == b"\x00" * 7


def test_string__load_null_default():
    field = fields.String(size=7, null_value=DEFAULT)
    assert field.from_bytes(b"\x00" * 7) is None


@pytest.mark.parametrize("null_value", (b"N\x00U\x00L\x00L\x00", "NULL"))
def test_string__null_value(null_value):
    field = fields.String(size=8, null_value=null_value, encoding="utf-16-le")
    assert field.from_bytes(b"N\x00U\x00L\x00L\x00") is None


def test_string__pad_byte_wrong_type():
    """Trying to pass a regular string as pad_byte will explode."""
    with pytest.raises(errors.ConfigurationError):
        stringlike.String(size=4, pad_byte=" ")


def test_string__pad_byte_too_long():
    """The padding byte must be exactly one byte."""
    with pytest.raises(errors.ConfigurationError):
        stringlike.String(size=4, pad_byte=b"0123")


def test_string__pad_default():
    """The default value should be padded if necessary."""
    field = stringlike.String(size=4, pad_byte=b" ", default="?")
    assert field.to_bytes() == b"?   "


def test_stringz__load_basic():
    """Basic test of StringZ loading."""
    field = stringlike.StringZ(encoding="utf-8")
    assert field.from_bytes(b"\xc2\xaf\\_(\xe3\x83\x84)_/\xc2\xaf\0") == r"¯\_(ツ)_/¯"


def test_stringz__load_eof_before_null():
    """Crash if we hit the end of the data before we get a null byte."""
    field = stringlike.StringZ(encoding="utf-8")
    with pytest.raises(errors.DeserializationError):
        assert field.from_bytes(b"\xc2\xaf\\_(\xe3\x83\x84)_/\xc2\xaf")


def test_stringz__dump_basic():
    """Basic test of StringZ dumping."""
    field = stringlike.StringZ(encoding="utf-8")
    assert field.to_bytes(r"¯\_(ツ)_/¯") == b"\xc2\xaf\\_(\xe3\x83\x84)_/\xc2\xaf\0"


def test_stringz__dump_multibyte():
    """Basic multibyte test dump."""
    field = stringlike.StringZ(encoding="utf-32-le")
    assert (
        field.to_bytes("AbC")
        == b"A\x00\x00\x00b\x00\x00\x00C\x00\x00\x00\x00\x00\x00\x00"
    )


def test_stringz__dump_multibyte_with_bom():
    """Ensure multibyte encodings work with StringZ as well and the BOM isn't
    added before the null byte."""
    field = stringlike.StringZ(encoding="utf-16")

    if sys.byteorder == "little":
        assert field.to_bytes("AbCd") == b"\xff\xfeA\x00b\x00C\x00d\x00\x00\x00"
    else:
        assert field.to_bytes("AbCd") == b"\xfe\xff\x00A\x00b\x00C\x00d\x00\x00"


def test_stringz_load_multibyte():
    """Test loading multibyte strings with a terminating null."""
    field = stringlike.StringZ(encoding="utf-16")
    assert field.from_bytes(b"\xff\xfeA\x00b\x00C\x00d\x00\x00\x00") == "AbCd"
    assert field.from_bytes(b"\xfe\xff\x00A\x00b\x00C\x00d\x00\x00") == "AbCd"


@pytest.mark.parametrize("null_value", (b"NULL\x00", "NULL"))
def test_stringz__load_null_value(null_value):
    field = stringlike.StringZ(null_value=null_value)
    assert field.from_bytes(b"NULL\x00") is None


def test_stringz__load_default_null_crashes():
    field = stringlike.StringZ(null_value=DEFAULT)
    with pytest.raises(errors.CannotDetermineNullError):
        field.from_bytes(b"\x00")


def test_stringz__dump_default_null_crashes():
    field = stringlike.StringZ(null_value=DEFAULT)
    with pytest.raises(errors.UnserializableValueError):
        field.to_bytes(None)
