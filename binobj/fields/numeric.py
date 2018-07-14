"""Fields representing numeric values, such as integers and floats."""

import struct
import sys
import warnings

from binobj import errors
from binobj.fields.base import Field
from binobj import helpers
from binobj import varints


__all__ = [
    'Float32', 'Float64',
    'Int8', 'Int16', 'Int32', 'Int64',
    'UInt8', 'UInt16', 'UInt32', 'UInt64',
    'Integer', 'UnsignedInteger', 'VariableLengthInteger',
]


class Float(Field):
    """A floating-point number in IEEE-754:2008 interchange format.

    This is a base class and should not be used directly.

    :param str endian:
        The endianness to use to load/store the float. Either 'big' or 'little'.
        If not given, defaults to the system's native byte ordering as given by
        :data:`sys.byteorder`.
    """
    def __init__(self, *, format_string, endian=None, **kwargs):
        super().__init__(size=struct.calcsize(format_string), **kwargs)

        self.endian = endian or sys.byteorder
        if self.endian == 'big':
            self.format_string = '>' + format_string
        elif self.endian == 'little':
            self.format_string = '<' + format_string
        else:
            raise ValueError("`endian` must be 'big' or 'little', got %r."
                             % endian)

    def _do_load(self, stream, context, loaded_fields):
        data = self._read_exact_size(stream)
        try:
            return struct.unpack(self.format_string, data)[0]
        except struct.error as exc:
            raise errors.DeserializationError(
                message=str(exc), field=self, data=data)

    def _do_dump(self, stream, data, context, all_fields):
        try:
            serialized = struct.pack(self.format_string, data)
        except struct.error as exc:
            raise errors.SerializationError(message=str(exc), field=self)
        stream.write(serialized)


class Float32(Float):
    """A floating-point number stored in IEEE-754 binary32 format."""
    def __init__(self, **kwargs):
        super().__init__(format_string='f', **kwargs)


class Float64(Float):
    """A floating-point number stored in IEEE-754 binary64 format."""
    def __init__(self, **kwargs):
        super().__init__(format_string='d', **kwargs)


class Integer(Field):
    """An integer.

    This is a base class and should not be used directly.

    :param str endian:
        The endianness to use to load/store the integer. Either 'big' or 'little'.
        If not given, defaults to the system's native byte ordering as given by
        :data:`sys.byteorder`.
    :param bool signed:
        Indicates if this number is a signed or unsigned integer. Defaults to
        ``True``.
    """
    def __init__(self, endian=None, signed=True, **kwargs):
        super().__init__(**kwargs)
        self.endian = endian or sys.byteorder
        self.signed = signed

    # pylint: disable=unused-argument

    def _do_load(self, stream, context, loaded_fields):
        """Load an integer from the given stream."""
        return helpers.read_int(stream, self.size, self.signed, self.endian)

    def _do_dump(self, stream, data, context, all_fields):
        """Dump an integer to the given stream."""
        return helpers.write_int(stream, data, self.size, self.signed,
                                 self.endian)

    # pylint: enable=unused-argument


class VariableLengthInteger(Integer):
    """An integer of varying size.

    :param VarIntEncoding vli_format:
        Required. The encoding to use for the variable-length integer.
    :param int max_bytes:
        The maximum number of bytes to use for encoding this integer. If not
        given, there's no restriction on the size.
    :param str endian:

        .. deprecated:: 0.4.3

            Since variable-length integer formats all specify an endianness, this
            argument is now ignored and will be removed in a later version.

    :param bool signed:
        If ``True``, this field is a signed integer.

        .. deprecated:: 0.4.3

            Since variable-length integer formats all specify a signedness, this
            argument is now ignored and will be removed in a later version.
    """
    def __init__(self, *, vli_format, max_bytes=None, endian=None, signed=None,
                 **kwargs):
        encoding_info = varints.INTEGER_ENCODING_MAP.get(vli_format)

        if encoding_info is None:
            raise errors.ConfigurationError(
                'Invalid or unsupported integer encoding scheme: %r' % vli_format,
                field=self)

        format_endianness = encoding_info['endian']
        format_signedness = encoding_info['signed']

        if signed is not None and signed != format_signedness:
            raise errors.ConfigurationError(
                "%s integers are %s, but signed=%r was passed to __init__()."
                % (vli_format, 'signed' if format_signedness else 'unsigned', signed),
                field=self)
        elif endian is not None and endian != format_endianness:
            raise errors.ConfigurationError(
                "%s integers are %s endian, but endian=%r was passed to __init__()."
                % (vli_format, format_endianness, endian),
                field=self)

        if signed is not None or endian is not None:
            warnings.warn('The `signed` and `endian` arguments are deprecated '
                          'and will be removed in a later version.',
                          DeprecationWarning)

        super().__init__(endian=format_endianness, signed=format_signedness,
                         **kwargs)

        self.vli_format = vli_format
        self.max_bytes = max_bytes
        self._encode_integer_fn = encoding_info['encode']
        self._decode_integer_fn = encoding_info['decode']

    # pylint: disable=unused-argument

    def _do_load(self, stream, context, loaded_fields):
        """Load a variable-length integer from the given stream."""
        return self._decode_integer_fn(stream)

    def _do_dump(self, stream, data, context, all_fields):
        """Dump an integer to the given stream."""
        try:
            encoded_int = self._encode_integer_fn(data)
        except (ValueError, OverflowError) as err:
            raise errors.UnserializableValueError(
                field=self, value=data, reason=str(err))

        if self.max_bytes is not None and len(encoded_int) > self.max_bytes:
            raise errors.ValueSizeError(field=self, value=data)

        stream.write(encoded_int)

    # pylint: enable=unused-argument

    def _size_for_value(self, value):
        return len(self._encode_integer_fn(value))


class UnsignedInteger(Integer):
    """An unsigned integer."""
    def __init__(self, **kwargs):
        super().__init__(signed=False, **kwargs)


class Int8(Integer):
    """An 8-bit signed integer."""
    def __init__(self, **kwargs):
        super().__init__(size=1, **kwargs)


class Int16(Integer):
    """A 16-bit signed integer."""
    def __init__(self, **kwargs):
        super().__init__(size=2, **kwargs)


class Int32(Integer):
    """A 32-bit signed integer."""
    def __init__(self, **kwargs):
        super().__init__(size=4, **kwargs)


class Int64(Integer):
    """A 64-bit signed integer."""
    def __init__(self, **kwargs):
        super().__init__(size=8, **kwargs)


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
