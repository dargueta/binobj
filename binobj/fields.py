"""Definitions of all field types that can be used in structures."""

# pylint: disable=too-few-public-methods

import sys

from binobj import errors
from binobj import helpers
from binobj import varints
from binobj import serialization

from binobj.serialization import DEFAULT
from binobj.serialization import UNDEFINED


class Field(serialization.Serializable):
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
    :param bytes null_value:
        A value to use to dump ``None``. When loading, the returned value will
        be ``None`` if this value is encountered.
    :param default:
        The default value to use if a value for this field isn't passed to the
        struct for serialization. If ``required`` is ``False`` and no default is
        given, null bytes will be used to fill the space required.

        This argument *must* be of the same type as the field, i.e. it must be
        a string for a :class:`String`, an integer for an :class:`Integer`, and
        so on.
    :param bool discard:
        When deserializing, don't include this field in the returned results.
    :param const:
        A constant value this field is expected to take. It will always have
        this value when dumped, and will fail validation if the field isn't this
        value when loaded. Useful for reserved fields and file tags.

        This argument *must* be of the same type as the field, i.e. it must be
        a string for a :class:`String`, an integer for an :class:`Integer`, and
        so on.

    .. attribute:: name

        The name of this field.

    .. attribute:: index

        The zero-based index of the field in the struct.

    .. attribute:: offset

        The zero-based byte offset of the field in the struct. If the offset
        can't be computed (e.g. it's preceded by a variable-length field), this
        will be ``None``.
    """
    def __init__(self, *, name=None, **kwargs):
        super().__init__(**kwargs)

        # These attributes are typically set by the struct containing the field
        # after the field's instantiated.
        self.name = name        # type: str
        self.index = None       # type: int
        self.offset = None      # type: int

    @property
    def const(self):
        return self.__options__.setdefault('const', UNDEFINED)

    @property
    def default(self):
        return self._get_default_value()

    @property
    def discard(self):
        return self.__options__.setdefault('discard', False)

    def load(self, stream, context=None):
        # TODO (dargueta): This try-catch just to set the field feels dumb.
        try:
            loaded_value = super().load(stream, context)
        except errors.DeserializationError as err:
            err.field = self
            raise

        # TODO (dargueta): Change this to a validator instead.
        if self.const is not UNDEFINED and loaded_value != self.const:
            raise errors.ValidationError(field=self, value=loaded_value)
        return loaded_value

    def dump(self, stream, data=DEFAULT, context=None):
        if data is DEFAULT:
            data = self.default
            if (data is UNDEFINED) or (data is DEFAULT):
                raise errors.MissingRequiredValueError(field=self)

        super().dump(stream, data, context)

    def __get__(self, instance, owner):
        if instance is None:
            return self

        return instance.__values__.setdefault(self.name, self.default)

    def __set__(self, instance, value):
        # TODO (dargueta): Call validators here
        instance.__values__[self.name] = value

    def __delete__(self, instance):
        instance.__values__[self.name] = self.default

    def __str__(self):
        return '%s(name=%r)' % (type(self).__name__, self.name)


class Array(Field):
    """An array of other serializable objects.

    :param binobj.serialization.Serializable component:
        The component this array is comprised of.
    :param int count:
        Optional. The number of elements in this array. If not given, the array
        is of variable size and ``halt_check`` should be passed in to indicate
        when the array ends.
    :param callable halt_check:
        A function taking four arguments. See :meth:`should_halt` for the
        default implementation. Subclasses can override this function if desired
        to avoid having to pass in a custom function every time.
    """
    def __init__(self, component, *, count=None, halt_check=None, **kwargs):
        self.component = component
        self.count = count
        self.halt_check = halt_check or self.should_halt
        super().__init__(**kwargs)

    @staticmethod
    def should_halt(seq, stream, loaded, context):    # pylint: disable=unused-argument
        """Determine if the deserializer should stop reading from the input.

        The default implementation does the following:

        - If the object has an integer attribute called ``count``, it compares
          ``count`` against the length of ``loaded``. If ``len(loaded)`` is less
          than ``count`` it'll return ``True`` (halt), ``False`` otherwise.
        - If the object *doesn't* have an attribute called ``count``, or
          ``count`` isn't an integer, the function returns ``True`` if there's
          any data left in the stream.

        :param Array seq:
            The sequence being checked.
        :param io.BytesIO stream:
            The data stream to read from. Except in rare circumstances, this is
            the same stream that was passed to :meth:`load`. The stream pointer
            should be returned to its original position when the function exits.
        :param list loaded:
            A list of the objects that have been deserialized so far. In general
            this function *should not* modify the list. A possible exception to
            this rule is to remove a sentinel value from the end of the list.
        :param context:
            The ``context`` object passed to :meth:`load`.

        :return: ``True`` if the deserializer should stop reading, ``False``
            otherwise.
        :rtype: bool
        """
        if isinstance(seq.count, int):
            return seq.count <= len(loaded)

        offset = stream.tell()
        try:
            return stream.read(1) == b''
        finally:
            stream.seek(offset)

    def _do_dump(self, stream, data, context):
        """Convert the given data into bytes and write it to ``stream``.

        :param io.BytesIO stream:
            A binary stream to write the serialized data into.
        :param list data:
            The data to dump.
        :param context:
            Additional data to pass to this method. Subclasses must ignore
            anything they don't recognize.
        """
        for value in data:
            self.component.dump(stream, value, context)

    def _do_load(self, stream, context=None):
        """Load a structure list from the given stream.

        :param io.BytesIO stream:
            A bit stream to read data from.
        :param context:
            Additional data to pass to this method. Subclasses must ignore
            anything they don't recognize.

        :return: The deserialized data.
        :rtype: list
        """
        result = []
        while not self.halt_check(self, stream, result, context):
            result.append(self.component.load(stream, context))

        return result


class Nested(Field):
    """Used for inserting nested structs."""
    def __init__(self, struct, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.struct = struct

    def _do_dump(self, stream, data, context):
        self.struct.dump(stream, data, context)

    def _do_load(self, stream, context):
        self.struct.load(stream, context)


class Bytes(Field):
    """Raw binary data."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.const is not UNDEFINED:
            self.size = len(self.const)

    def _do_load(self, stream, context):    # pylint: disable=unused-argument
        return stream.read(self.size)


class Integer(Field):
    """An integer.

    :param str endian:
        The endianness to use to load/store the integer. Either 'big' or 'little'.
        If not given, defaults to the system's native byte ordering as given by
        :data:`sys.byteorder`.
    :param bool signed:
        Indicates if this number is a signed or unsigned integer. Defaults to
        ``True``.
    """
    @property
    def endian(self):
        """The endianness to use to load/store the integer.

        :type: str
        """
        return self.__options__.setdefault('endian', sys.byteorder)

    @property
    def signed(self):
        """Indicates if this number is a signed or unsigned integer.

        :type: bool
        """
        return self.__options__.setdefault('signed', True)

    def _do_load(self, stream, context):     # pylint: disable=unused-argument
        """Load an integer from the given stream."""
        return helpers.read_int(stream, self.size, self.signed, self.endian)

    def _do_dump(self, stream, value, context):  # pylint: disable=unused-argument
        """Dump an integer to the given stream."""
        return helpers.write_int(stream, value, self.size, self.signed,
                                 self.endian)


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
    def __init__(self, *args, encoding, signed=True, **kwargs):
        if encoding == varints.VarIntEncoding.VLQ and signed is True:
            raise errors.FieldConfigurationError(
                "Signed integers can't be encoded with VLQ. Either pass "
                "`signed=False` to __init__ or use an encoding that works for "
                "signed integers, like %s."
                % varints.VarIntEncoding.COMPACT_INDICES,
                field=self)

        encoding_functions = varints.INTEGER_ENCODING_MAP.get(encoding)
        if encoding_functions is None:
            raise errors.FieldConfigurationError(
                'Invalid or unsupported integer encoding scheme: %r' % encoding,
                field=self)

        self._encode_integer_fn = encoding_functions['encode']
        self._decode_integer_fn = encoding_functions['decode']
        super().__init__(*args,
                         endian=encoding_functions['endian'],
                         signed=signed,
                         encoding=encoding,
                         **kwargs)

    @property
    def encoding(self):
        """The encoding to use for the variable-length integer.

        :type: str
        """
        return self.__options__['encoding']

    @property
    def max_bytes(self):
        """The maximum number of bytes to use for encoding this integer, or
        ``None`` if there's no limit.

        :type: int
        """
        return self.__options__['max_bytes']

    def _do_load(self, stream, context):   # pylint: disable=unused-argument
        """Load a variable-length integer from the given stream."""
        return self._decode_integer_fn(self, stream)

    def _do_dump(self, stream, value, context):    # pylint: disable=unused-argument
        """Dump an integer to the given stream."""
        try:
            stream.write(self._encode_integer_fn(value))
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


class String(Field):
    """A fixed-length string.

    :param str encoding:
        The encoding to use for converting the string to and from bytes.
    :param bool truncate:
        If ``True``, strings too long to fit into the defined field size will be
        truncated to fit. If ``False`` (the default) a :class:`ValueSizeError`
        will be thrown.

    .. note::

        A fixed-width text encoding such as ASCII or ISO-8859-1 is *strongly*
        recommended when using ``truncate`` or ``fill_byte``, since truncating
        can result in an invalid string.

        It's up to the user to ensure that the text encoding's restrictions are
        obeyed, e.g. that the field length is a multiple of two if you select
        ``utf-16`` as the encoding.
    """
    @property
    def encoding(self):
        """The encoding to use for this string.
        Defaults to ``ascii``.

        :type: str
        """
        return self.__options__.setdefault('encoding', 'ascii')

    @property
    def truncate(self):
        """When serializing, truncate strings that are too long to fit into the
        field. Defaults to ``False``.

        :type: bool
        """
        return self.__options__.setdefault('truncate', False)

    def _do_load(self, stream, context):  # pylint: disable=unused-argument
        """Load a fixed-length string from a stream."""
        to_load = self._read_exact_size(stream)
        return to_load.decode(self.encoding)

    def _do_dump(self, stream, value, context):  # pylint: disable=unused-argument
        """Dump a fixed-length string into the stream."""
        to_dump = value.encode(self.encoding)

        if len(to_dump) > self.size and not self.truncate:
            raise errors.ValueSizeError(field=self, value=to_dump)
        elif len(to_dump) < self.size:
            raise errors.ValueSizeError(field=self, value=to_dump)
        else:
            to_dump = to_dump[:self.size]

        stream.write(to_dump)


class StringZ(String):
    """A variable-length null-terminated string.

    This field currently only works for string encodings that encode a null as
    a single byte, such as ASCII, ISO-8859-1, and UTF-8.

    .. warning::

        This will fail for encodings using multiple bytes to represent a null,
        such as UTF-16 and UTF-32.
    """
    def _do_load(self, stream, context):
        string = bytearray()
        char = stream.read(1)

        while char != b'\0':
            if char == b'':
                raise errors.UnexpectedEOFError(
                    field=self, size=1, offset=stream.tell())
            string.append(char)
            char = stream.read(1)

        return string.decode(self.encoding)

    def _do_dump(self, stream, value, context):
        stream.write(value.encode(self.encoding) + b'\0')
