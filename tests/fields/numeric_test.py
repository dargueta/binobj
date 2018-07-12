import pytest

from binobj import errors
from binobj import varints
from binobj.fields import numeric


def test_const_set_size__varint():
    """Variable integers should set their size when ``const`` is defined."""
    field = numeric.VariableLengthInteger(vli_format=varints.VarIntEncoding.VLQ,
                                          const=987654321)
    assert field.size == 5


def test_varint__signed_crash():
    """Crash when creating a signed variable-length integer using an encoding
    that doesn't support signed values."""
    with pytest.raises(errors.ConfigurationError) as errinfo:
        numeric.VariableLengthInteger(vli_format=varints.VarIntEncoding.VLQ,
                                      signed=True)

    assert str(errinfo.value).startswith("VarIntEncoding.VLQ integers are unsigned")


def test_varint__endian_crash():
    """Crash when creating a little-endian variable-length integer using a big-
    endian encoding."""
    with pytest.raises(errors.ConfigurationError) as errinfo:
        numeric.VariableLengthInteger(vli_format=varints.VarIntEncoding.VLQ,
                                      endian='little')

    assert str(errinfo.value).startswith("VarIntEncoding.VLQ integers are big endian")


@pytest.mark.parametrize('kwargs', (
    {'vli_format': varints.VarIntEncoding.LEB128, 'endian': 'little'},
    {'vli_format': varints.VarIntEncoding.VLQ, 'signed': False},
))
def test_varint__explicit_signed_or_endian_warns(kwargs):
    """The signed and endian kwargs are deprecated for varints."""
    with pytest.warns(DeprecationWarning):
        numeric.VariableLengthInteger(**kwargs)


def test_varint__unsupported_encoding():
    """Crash if we try using an unsupported VarInt encoding."""
    with pytest.raises(errors.ConfigurationError) as errinfo:
        numeric.VariableLengthInteger(vli_format='uleb128')

    assert str(errinfo.value).startswith('Invalid or unsupported integer')


@pytest.mark.parametrize('value,expected', (
    (127, b'\x7f'),
    (0x1234567890, b'\x82\xa3\xa2\xd9\xf1\x10'),
))
def test_varint__basic_dump(value, expected):
    """Test VLQ dump.

    We know that our codecs work (see varints_test.py) so here we're doing a
    perfunctory test to make sure dumping works as expected.
    """
    field = numeric.VariableLengthInteger(vli_format=varints.VarIntEncoding.VLQ)
    assert field.dumps(value) == expected


@pytest.mark.parametrize('data, expected', (
    (b'\x3f', 0x3f),
))
def test_varint__basic_load(data, expected):
    """Test VLQ load."""
    field = numeric.VariableLengthInteger(vli_format=varints.VarIntEncoding.VLQ)
    assert field.loads(data) == expected


def test_varint__overflow():
    """Crash if we try to zigzag an integer that's too big."""
    field = numeric.VariableLengthInteger(vli_format=varints.VarIntEncoding.ZIGZAG)

    with pytest.raises(errors.UnserializableValueError):
        field.dumps(2**65)


def test_varint__max_bytes():
    """Crash if a variable-length integer takes up too many bytes."""
    field = numeric.VariableLengthInteger(vli_format=varints.VarIntEncoding.VLQ,
                                          max_bytes=2)

    with pytest.raises(errors.ValueSizeError):
        field.dumps(100000)


@pytest.mark.parametrize('value, expected', (
    (3.141592654, b'\xdb\x0f\x49\x40'),
    (100, b'\x00\x00\xc8\x42'),
    (2 ** 31, b'\x00\x00\x00\x4f'),
    (float('inf'), b'\x00\x00\x80\x7f'),
    (-float('inf'), b'\x00\x00\x80\xff'),
    (float('nan'), b'\x00\x00\xc0\x7f'),
))
def test_float32__dumps__basic_le(value, expected):
    field = numeric.Float32(endian='little')
    assert field.dumps(value) == expected


def test_float32__dumps__basic_be():
    field = numeric.Float32(endian='big')
    assert field.dumps(2 ** 31) == b'\x4f\x00\x00\x00'


@pytest.mark.parametrize('value, expected', (
    (3.141592654, b'\x40\x09\x21\xfb\x54\x52\x45\x50'),
    (100, b'\x40\x59\x00\x00\x00\x00\x00\x00'),
    (2 ** 31, b'\x41\xe0\x00\x00\x00\x00\x00\x00'),
    (float('inf'), b'\x7f\xf0\x00\x00\x00\x00\x00\x00'),
    (-float('inf'), b'\xff\xf0\x00\x00\x00\x00\x00\x00'),
    (float('nan'), b'\x7f\xf8\x00\x00\x00\x00\x00\x00'),
))
def test_float64__dumps__basic_be(value, expected):
    field = numeric.Float64(endian='big')
    assert field.dumps(value) == expected


def test_float64__dumps__basic_le():
    field = numeric.Float64(endian='little')
    assert field.dumps(2 ** 31) == b'\x00\x00\x00\x00\x00\x00\xe0\x41'
