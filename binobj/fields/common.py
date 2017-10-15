"""Commonly-used field definitions provided for convenience.

These are built on top of the base fields defined in :mod:`binobj.fields.bases`.
For example, :class:`UInt16` is equivalent to ``Integer(n_bytes=2, signed=False)``
but is more readable and shorter to write.
"""

import sys

import bitstring

from binobj import errors
from binobj import varints
from binobj.fields import bases


_BIT_VALUE_ATTR = {
    ('little', True): 'intle',
    ('little', False): 'uintle',
    ('big', True): 'intbe',
    ('big', False): 'uintbe',
}


class Bytes(bases.Field):   # pylint: disable=too-few-public-methods
    """Raw binary data."""
    UNDERLYING_TYPE = bytes


class Integer(bases.Field):
    """An integer.

    :param str endian:
        The endianness to use to load/store the integer. Either 'big' or 'little'.
        If not given, defaults to the system's native byte ordering.
    :param bool signed:
        Indicates if this number is a signed or unsigned integer.
    """
    UNDERLYING_TYPE = int

    def __init__(self, *, endian=None, signed=True, **kwargs):
        self.signed = signed
        self.endian = endian or sys.byteorder

        key = (self.endian, self.signed)
        if key not in _BIT_VALUE_ATTR:
            raise OSError(
                'Unrecognized combination of endianness (%r) and signedness (%r). '
                'Either this is running on a mixed-endian system or an invalid '
                'value for `endian` was passed in.'% (self.endian, self.signed))

        self._value_attr = _BIT_VALUE_ATTR[key]

        super().__init__(**kwargs)

    def load(self, stream, context=None):
        """Load an integer from the given stream.

        :param bitstring.BitStream stream:
            The stream to load from.
        :param context:
            Additional information to pass to this method.
        """
        bits = self._read_exact_size(stream)
        if self._n_bits % 8 == 0:
            return getattr(bits, self._value_attr)

        # Else: integer isn't a whole number of bytes. We need to pad the loaded
        # value with bits, either copying the sign bit or padding with zeros
        # depending on whether it's signed or not.
        raise NotImplementedError

    def dump(self, value, stream, context=None):  # pylint: disable=unused-argument
        """Dump an integer to the given stream.

        :param int value:
            The value to dump into the stream.
        :param bitstring.BitStream stream:
            The stream to write to.
        :param context:
            Additional information to pass to this method.
        """
        kwarg = {self._value_attr: value}
        bits = bitstring.Bits(length=self._n_bits, **kwarg)
        stream.insert(bits)


class VariableLengthInteger(Integer):
    """An integer of varying size.

    :param VarIntEncoding encoding:
        The encoding to use for the variable-length integer.
    :param int size:
        The maximum number of bytes to use for encoding this integer.
    :param bool signed:
        If ``True``, this field is a signed integer.
    """
    def __init__(self, *, encoding, max_size=None, signed=True, **kwargs):
        if encoding == varints.VarIntEncoding.VLQ and signed is True:
            raise errors.FieldConfigurationError(
                "Signed integers can't be encoded with VLQ. Use an encoding "
                "that supports signed integers, like %s."
                % varints.VarIntEncoding.COMPACT_INDICES,
                field=self)

        self.encoding = encoding
        self.max_size = max_size

        encoding_functions = varints.INTEGER_ENCODING_MAP.get(encoding)
        if encoding_functions is None:
            raise errors.FieldConfigurationError(
                'Invalid or unsupported integer encoding scheme: %r' % encoding,
                field=self)

        self._encode_integer_fn = encoding_functions['encode']
        self._decode_integer_fn = encoding_functions['decode']
        super().__init__(endian=encoding_functions['endian'],
                         signed=signed,
                         **kwargs)

    def load(self, stream, context=None):   # pylint: disable=unused-argument
        """Load a variable-length integer from the given stream."""
        return self._decode_integer_fn(self, stream)

    def dump(self, value, stream, context=None):    # pylint: disable=unused-argument
        """Dump an integer to the given stream."""
        if value is None:
            stream.insert(self._get_null_value())
        else:
            stream.insert(self._encode_integer_fn(self, value))


class UnsignedInteger(Integer):
    """An unsigned integer."""
    def __init__(self, **kwargs):
        super().__init__(signed=False, **kwargs)


class Int8(Integer):
    """An 8-bit signed integer."""
    def __init__(self, **kwargs):
        super().__init__(n_bytes=1, **kwargs)


class Int16(Integer):
    """A 16-bit signed integer."""
    def __init__(self, **kwargs):
        super().__init__(n_bytes=2, **kwargs)


class Int32(Integer):
    """A 32-bit signed integer."""
    def __init__(self, **kwargs):
        super().__init__(n_bytes=4, **kwargs)


class Int64(Integer):
    """A 64-bit signed integer."""
    def __init__(self, **kwargs):
        super().__init__(n_bytes=8, **kwargs)


class UInt8(Int8):
    """An 8-bit unsigned integer."""
    def __init__(self, **kwargs):
        super().__init__(signed=False, **kwargs)


class UInt16(Int16):
    """A 16-bit unsigned integer."""
    def __init__(self, **kwargs):
        super().__init__(signed=False, **kwargs)


class UInt32(Int32):
    """A 32-bit unsigned integer."""
    def __init__(self, **kwargs):
        super().__init__(signed=False, **kwargs)


class UInt64(Int64):
    """A 64-bit unsigned integer."""
    def __init__(self, **kwargs):
        super().__init__(signed=False, **kwargs)


class String(bases.Field):
    """A fixed-length string."""
    UNDERLYING_TYPE = str

    def __init__(self, *, encoding='utf-8', truncate=False, pad_byte=None, **kwargs):
        self.encoding = encoding
        self.truncate = truncate
        self.pad_byte = pad_byte
        super().__init__(**kwargs)

    def load(self, stream, context=None):  # pylint: disable=unused-argument
        """Load a fixed-length string from a stream."""
        to_load = self._read_exact_size(stream)
        return to_load.tobytes().decode(self.encoding)

    def dump(self, value, stream, context=None):  # pylint: disable=unused-argument
        """Dump a fixed-length string into the stream."""
        if value is None:
            to_dump = self._get_null_value()
        else:
            to_dump = value.encode(self.encoding)
            if len(to_dump) > self._n_bytes and not self.truncate:
                raise errors.ValueSizeError(field=self, value=to_dump)
            elif len(to_dump) < self._n_bytes:
                if self.pad_byte is None:
                    raise errors.ValueSizeError(field=self, value=to_dump)
                to_dump += (self.pad_byte * (self._n_bytes - len(to_dump)))
            else:
                to_dump = to_dump[:self._n_bytes]

        stream.insert(to_dump)


class StringZ(String):
    """A variable-length null-terminated string."""
    def load(self, stream, context=None):
        string = b''
        char = stream.read(8)

        while char != b'\0':
            if char == b'':
                raise errors.UnexpectedEOFError(
                    field=self, size=1, offset=stream.pos)
            string += char.tobytes()
            char = stream.read(8)

        return string.decode(self.encoding)

    def dump(self, value, stream, context=None):
        if value is None:
            stream.insert(self._get_null_value())
        else:
            stream.insert(value.encode(self.encoding) + b'\0')
