"""Definitions of all field types that can be used in structures."""

# pylint: disable=too-few-public-methods

import sys

import bitstring

from binobj import errors
from binobj import varints
from binobj import serialization


class Field(serialization.SerializableScalar):
    """The base class for all struct fields.

    :param str name:
        The name of the field.
    :param bool required:
        If ``True``, this value *must* be passed to the serializer for a struct.
        If ``False``, the default value will be used if the field is missing in
        a call to :meth:`dump`.
    :param bool allow_null:
        If ``True`` (the default) then ``None`` is an acceptable value to write
        for this field.
    :param null_value:
        A value to use to dump ``None``. When loading, the returned value will
        be ``None`` if this value is encountered. You can pass either
        :class:`bytes` or a :class:`bitstring.Bits` object.
    :param default:
        The default value to use if a value for this field isn't passed to the
        struct for serialization. If ``required`` is ``False`` and no default is
        given, null bytes will be used to fill the space required.
    :param bool discard:
        When deserializing, don't include this field in the returned results.
    """
    def __init__(self, *, name=None, required=True, allow_null=True,
                 null_value=serialization.DEFAULT, discard=False, **kwargs):
        if not allow_null and null_value is serialization.DEFAULT:
            null_value = serialization.UNDEFINED

        self.name = name
        self.required = required
        self.discard = discard

        # The following fields are set by the struct metaclass after the field
        # is instantiated.

        #: A weak reference to the :class:`~binobj.structures.Struct` class
        #: containing this field.
        self.struct_class = None    # type: binobj.structures.Struct

        #: The zero-based index of the field in the struct.
        self.index = None   # type: int

        #: The zero-based bit offset of the field in the struct. If the offset
        #: can't be computed (e.g. it's preceded by a variable-length field),
        #: this will be ``None``.
        self.offset = None  # type: int

        super().__init__(allow_null=allow_null, null_value=null_value, **kwargs)

    def __str__(self):
        return '%s::%s(name=%r)' % (
            (self.struct_class.__name__, type(self).__name__, self.name))


_BIT_VALUE_ATTR = {
    ('little', True): 'intle',
    ('little', False): 'uintle',
    ('big', True): 'intbe',
    ('big', False): 'uintbe',
}


class Const(Field):
    """A field that expects an invariable hard-coded value.

    A common use for this field is to validate the "magic number" of a file.
    """
    def __init__(self, value, **kwargs):
        self.value = value

        if isinstance(value, bitstring.Bits):
            n_bits = value.length
        elif isinstance(value, (bytes, bytearray)):
            n_bits = len(value) * 8
        else:
            raise TypeError(
                'Expected `bitstring.Bits`, `bytes`, or `bytearray`, got %r.'
                % type(value).__name__)

        super().__init__(n_bits=n_bits, **kwargs)


class Bytes(Field):
    """Raw binary data."""


class Integer(Field):
    """An integer.

    :param str endian:
        The endianness to use to load/store the integer. Either 'big' or 'little'.
        If not given, defaults to the system's native byte ordering.
    :param bool signed:
        Indicates if this number is a signed or unsigned integer.
    """
    def __init__(self, *, endian=None, signed=True, **kwargs):
        self.signed = signed
        self.endian = endian or sys.byteorder

        key = (self.endian, self.signed)
        if key not in _BIT_VALUE_ATTR:
            raise ValueError(
                'Unrecognized combination of endianness (%r) and signedness (%r). '
                'Either this is running on a mixed-endian system or an invalid '
                'value for `endian` or `signed` was passed in.' % key)

        self._value_attr = _BIT_VALUE_ATTR[key]

        super().__init__(**kwargs)

    def load(self, stream, context=None):     # pylint: disable=unused-argument
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
    :param int max_bytes:
        The maximum number of bytes to use for encoding this integer. If not
        given, there's no restriction on the size.
    :param bool signed:
        If ``True``, this field is a signed integer.

    .. note::
        Not all integer encodings allow signed integers.
    """
    def __init__(self, *, encoding, max_bytes=None, signed=True, **kwargs):
        if encoding == varints.VarIntEncoding.VLQ and signed is True:
            raise errors.FieldConfigurationError(
                "Signed integers can't be encoded with VLQ. Use an encoding "
                "that supports signed integers, like %s."
                % varints.VarIntEncoding.COMPACT_INDICES,
                field=self)

        self.encoding = encoding
        self.max_bytes = max_bytes

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
        try:
            return self._decode_integer_fn(self, stream)
        except bitstring.ReadError:
            raise errors.UnexpectedEOFError(field=self, size=8, offset=stream.pos)

    def dump(self, value, stream, context=None):    # pylint: disable=unused-argument
        """Dump an integer to the given stream."""
        if value is None:
            stream.insert(self._get_null_value())
            return

        try:
            stream.insert(self._encode_integer_fn(value))
        except bitstring.ReadError:
            raise errors.UnexpectedEOFError(field=self, size=8, offset=stream.pos)
        except ValueError as err:
            raise errors.UnserializableValueError(
                field=self, value=value, reason=str(err))


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


class String(Field):
    """A fixed-length string.

    :param str encoding:
        The encoding to use for converting the string to and from bytes.
    :param bool truncate:
        If ``True``, strings too long to fit into the defined field size will be
        truncated to fit. If ``False`` (the default) a :class:`ValueSizeError`
        will be thrown.
    :param bytes fill_byte:
        A single byte to use for padding.

    .. note::

        A fixed-width text encoding such as ASCII or ISO-8859-1 is *strongly*
        recommended when using ``truncate`` or ``fill_byte``, since truncating
        or padding can result in an invalid string.

        It's up to the user to ensure that the text encoding's restrictions are
        obeyed, e.g. that the field length is a multiple of two if you select
        ``utf-16`` as the encoding.
    """
    def __init__(self, *, encoding='ascii', truncate=False, fill_byte=None,
                 align_left=True, **kwargs):
        if fill_byte is not None and len(fill_byte) != 1:
            raise ValueError(
                '`fill_byte` must be exactly one byte, got %r.' % fill_byte)

        self.encoding = encoding
        self.truncate = truncate
        self.fill_byte = fill_byte
        self.align_left = align_left
        super().__init__(**kwargs)

    def load(self, stream, context=None):  # pylint: disable=unused-argument
        """Load a fixed-length string from a stream."""
        to_load = self._read_exact_size(stream)
        return to_load.bytes.decode(self.encoding)

    def dump(self, value, stream, context=None):  # pylint: disable=unused-argument
        """Dump a fixed-length string into the stream."""
        if value is None:
            to_dump = self._get_null_value()
        else:
            to_dump = value.encode(self.encoding)
            if len(to_dump) > self._n_bytes and not self.truncate:
                raise errors.ValueSizeError(field=self, value=to_dump)
            elif len(to_dump) < self._n_bytes:
                if self.fill_byte is None:
                    raise errors.ValueSizeError(field=self, value=to_dump)

                padding = (self.fill_byte * (self._n_bytes - len(to_dump)))
                if self.align_left:
                    to_dump += padding
                else:
                    to_dump = padding + to_dump
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
