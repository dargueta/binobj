"""Definitions of all field types that can be used in structures."""


import abc
import codecs
import collections
import collections.abc
import io
import sys

from binobj import errors
from binobj import helpers
from binobj import varints


class _NamedSentinel:   # pylint: disable=too-few-public-methods
    """An object type used for creating sentinel objects that can be retrieved
    by name.
    """
    # A mapping of sentinels from name to instance.
    __sentinels = {}

    def __init__(self, name):
        self.name = name

    @classmethod
    def get_sentinel(cls, name):
        """Return the sentinel with the given name, creating it if necessary."""
        return cls.__sentinels.setdefault(name, cls(name))

    def __deepcopy__(self, memodict=None):
        return self

    def __repr__(self):     # pragma: no cover
        return 'Sentinel(%r)' % self.name


#: A sentinel value used to indicate that a setting or field is undefined.
UNDEFINED = _NamedSentinel.get_sentinel('UNDEFINED')


#: A sentinel value used to indicate that the default value of a setting should
#: be used. We need this because sometimes ``None`` is a valid value for that
#: setting.
DEFAULT = _NamedSentinel.get_sentinel('DEFAULT')


class Field:
    """The base class for all struct fields.

    :param str name:
        The name of the field.
    :param const:
        A constant value this field is expected to take. It will always have
        this value when dumped, and will fail validation if the field isn't this
        value when loaded. Useful for reserved fields and file tags.

        This argument *must* be of the same type as the field, i.e. it must be
        a string for a :class:`String`, an integer for an :class:`Integer`, and
        so on.
    :param default:
        The default value to use if a value for this field isn't passed to the
        struct for serialization, or a callable taking no arguments that will
        return a default value.

        This argument (or the return value of the callable) *must* be of the
        same type as the field, i.e. it must be a string for a :class:`String`,
        an integer for an :class:`Integer`, and so on.
    :param bool discard:
        When deserializing, don't include this field in the returned results.
    :param bytes null_value:
        A value to use to dump ``None``. When loading, the returned value will
        be ``None`` if this value is encountered.

    .. attribute:: index

        The zero-based index of the field in the struct.

        :type: int

    .. attribute:: offset

        The zero-based byte offset of the field in the struct. If the offset
        can't be computed (e.g. it's preceded by a variable-length field), this
        will be ``None``.

        :type: int

    .. attribute:: size

        The size of this object, in bytes.

        :type: int
    """
    def __init__(self, *, name=None, const=UNDEFINED, default=UNDEFINED,
                 discard=False, null_value=UNDEFINED, size=None):
        self.const = const
        self.discard = discard
        self.null_value = null_value

        if default is UNDEFINED and const is not UNDEFINED:
            # If no default is given but ``const`` is, set the default value to
            # ``const``.
            self._default = const
        else:
            self._default = default

        if size is None and isinstance(const, collections.abc.Sized):
            self.size = len(const)
        else:
            self.size = size

        # These attributes are typically set by the struct containing the field
        # after the field's instantiated.
        self.name = name        # type: str
        self.index = None       # type: int
        self.offset = None      # type: int

    def bind_to_container(self, name, index, offset=None):
        """Bind this field to a container class.

        :param str name:
            The name of this field.
        :param int index:
            The index of this field in the container.
        :param int offset:
            The byte offset of this field in the container, or ``None`` if
            unknown. This is usually equal to the sum of the sizes of the fields
            preceding this one in the container.
        """
        # Don't rebind this field to a different class. This can happen if a
        # container class is subclassed.
        if self.name is not None:
            return

        self.name = name
        self.index = index
        self.offset = offset

    @property
    def allow_null(self):
        """Is ``None`` an acceptable value for this field?

        :rtype: bool
        """
        return self.null_value is not UNDEFINED

    @property
    def default(self):
        """The default value of this field, or :data:`UNDEFINED`.

        If the default value passed to the constructor was a callable, this
        property will always give its return value. That callable is invoked on
        each access of this property.
        """
        default_value = self._default
        if callable(default_value):
            return default_value()
        return default_value

    @property
    def required(self):
        """Is this field required for serialization?

        :type: bool
        """
        return self.const is UNDEFINED and self.default is UNDEFINED

    def load(self, stream, context=None, loaded_fields=None):
        """Load data from the given stream.

        :param io.BufferedIOBase stream:
            The stream to load data from.
        :param context:
            Additional data to pass to this method. Subclasses must ignore
            anything they don't recognize.
        :param dict loaded_fields:
            A dictionary of the fields that have already been loaded. This is
            set automatically when a field is loaded by a :class:`~binobj.Struct`.

        :return: The deserialized data.
        """
        # TODO (dargueta): This try-catch just to set the field feels dumb.
        try:
            loaded_value = self._do_load(stream, context=context,
                                         loaded_fields=loaded_fields)
        except errors.DeserializationError as err:
            err.field = self
            raise

        if loaded_value == self.null_value:
            return None

        # TODO (dargueta): Change this to a validator instead.
        if self.const is not UNDEFINED and loaded_value != self.const:
            raise errors.ValidationError(field=self, value=loaded_value)
        return loaded_value

    def loads(self, data, context=None, exact=True, loaded_fields=None):
        """Load from the given byte string.

        :param bytes data:
            A bytes-like object to get the data from.
        :param context:
            Additional data to pass to this method. Subclasses must ignore
            anything they don't recognize.
        :param bool exact:
            ``data`` must contain exactly the number of bytes required. If not
            all the bytes in ``data`` were used when reading the struct, throw
            an exception.
        :param dict loaded_fields:
            A dictionary of the fields that have already been loaded. This is
            set automatically when a field is loaded by a :class:`~binobj.Struct`.

        :return: The deserialized data.
        """
        if loaded_fields is None:
            loaded_fields = {}

        stream = io.BytesIO(data)
        loaded_data = self.load(stream, context=context, loaded_fields=loaded_fields)

        if exact and (stream.tell() < len(data)):
            # TODO (dargueta): Better error message.
            raise errors.ExtraneousDataError(
                'Expected to read %d bytes, read %d.'
                % (stream.tell(), len(data)))
        return loaded_data

    @abc.abstractmethod
    def _do_load(self, stream, context, loaded_fields):
        """Load an object from the stream.

        :param io.BufferedIOBase stream:
        :param context:
            Additional data to pass to this method. Subclasses must ignore
            anything they don't recognize.
        :param dict loaded_fields:
            A dictionary of the fields that have already been loaded. This is
            guaranteed to not be ``None``.

        :return: The loaded object.
        """
        raise NotImplementedError

    def dump(self, stream, data=DEFAULT, context=None, all_fields=None):
        """Convert the given data into bytes and write it to ``stream``.

        :param io.BufferedIOBase stream:
            The stream to write the serialized data into.
        :param data:
            The data to dump. Can be omitted only if this is a constant field or
            if a default value is defined.
        :param context:
            Additional data to pass to this method. Subclasses must ignore
            anything they don't recognize.
        :param dict all_fields:
            A dictionary of the fields about to be dumped. This is set
            automatically by the field's containing :class:`~binobj.Struct`.
        """
        if all_fields is None:
            all_fields = {}

        if data is DEFAULT:
            data = self.default
            if data in (UNDEFINED, DEFAULT):
                raise errors.MissingRequiredValueError(field=self)
        elif data is None:
            data = self._get_null_value()

        self._do_dump(stream, data, context=context, all_fields=all_fields)

    def dumps(self, data=DEFAULT, context=None, all_fields=None):
        """Convert the given data into bytes.

        :param data:
            The data to dump. Can be omitted only if this is a constant field or
            a default value is defined.
        :param context:
            Additional data to pass to this method. Subclasses must ignore
            anything they don't recognize.
        :param dict all_fields:
            A dictionary of the fields about to be dumped. This is set
            automatically by the field's containing :class:`~binobj.Struct`.

        :return: The serialized data.
        :rtype: bytes
        """
        stream = io.BytesIO()
        self.dump(stream, data, context=context, all_fields=all_fields)
        return stream.getvalue()

    @abc.abstractmethod
    def _do_dump(self, stream, data, context, all_fields):
        """Write the given data to the byte stream.

        :param io.BufferedIOBase stream:
            The stream to write to.
        :param data:
            The data to dump. Guaranteed to not be ``None``.
        :param context:
            Additional data to pass to this method. Subclasses must ignore
            anything they don't recognize.
        :param dict all_fields:
            A dictionary of the fields about to be dumped. This is guaranteed to
            not be ``None``.
        """
        raise errors.UnserializableValueError(field=self, value=data)

    def _get_null_value(self):
        """Return the serialized value for ``None``.

        We need this function because there's some logic involved in determining
        if ``None`` is a legal value, and guessing the serialization if no
        default value is provided.

        :return: The serialized form of ``None`` for this field.
        :rtype: bytes
        """
        if not self.allow_null:
            raise errors.UnserializableValueError(
                reason='`None` is not an acceptable value for %s.' % self,
                field=self,
                value=None)
        elif self.null_value is not DEFAULT:
            return self.null_value

        # User wants us to use all null bytes for the default null value.
        if self.size is None:
            raise errors.UnserializableValueError(
                reason="Can't guess appropriate serialization of `None` for %s "
                       "because it has no fixed size." % self,
                field=self,
                value=None)

        return b'\0' * self.size

    def _read_exact_size(self, stream):
        """Read exactly the number of bytes this object takes up or crash.

        :param io.BufferedIOBase stream: The stream to read from.

        :return: Exactly ``self.size`` bytes are read from the stream.
        :rtype: bytes

        :raise VariableSizedFieldError:
            The field cannot be read directly because it's of variable size.
        :raise UnexpectedEOFError: Not enough bytes were left in the stream.
        """
        offset = stream.tell()
        n_bytes = self.size

        if n_bytes is None:
            raise errors.VariableSizedFieldError(field=self, offset=offset)

        data_read = stream.read(n_bytes)
        if len(data_read) < n_bytes:
            raise errors.UnexpectedEOFError(
                field=self, size=n_bytes, offset=offset)

        return data_read

    def __get__(self, instance, owner):
        if instance is None:
            return self
        return instance.__values__.setdefault(self.name, self.default)

    def __set__(self, instance, value):
        # TODO (dargueta): Call validators here
        instance.__values__[self.name] = value

    def __str__(self):
        return '%s(name=%r)' % (type(self).__name__, self.name)


class Array(Field):
    """An array of other serializable objects.

    :param Field component:
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
        super().__init__(**kwargs)
        self.component = component
        self.count = count
        self.halt_check = halt_check or self.should_halt

    @staticmethod
    def should_halt(seq, stream, values, context, loaded_fields):    # pylint: disable=unused-argument
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
        :param io.BufferedIOBase stream:
            The data stream to read from. Except in rare circumstances, this is
            the same stream that was passed to :meth:`load`. The stream pointer
            should be returned to its original position when the function exits.
        :param list values:
            A list of the objects that have been deserialized so far. In general
            this function *should not* modify the list. A possible exception to
            this rule is to remove a sentinel value from the end of the list.
        :param context:
            The ``context`` object passed to :meth:`load`.
        :param dict loaded_fields:
            The fields in the struct that have been loaded so far.

        :return: ``True`` if the deserializer should stop reading, ``False``
            otherwise.
        :rtype: bool
        """
        if isinstance(seq.count, int):
            return seq.count <= len(values)

        offset = stream.tell()
        try:
            return stream.read(1) == b''
        finally:
            stream.seek(offset)

    def _do_dump(self, stream, data, context, all_fields):
        """Convert the given data into bytes and write it to ``stream``.

        :param io.BufferedIOBase stream:
            A binary stream to write the serialized data into.
        :param list data:
            The data to dump.
        :param context:
            Additional data to pass to this method. Subclasses must ignore
            anything they don't recognize.
        :param dict all_fields:
            A dictionary of the fields about to be dumped. This is guaranteed to
            not be ``None``.
        """
        for value in data:
            self.component.dump(stream, value, context=context,
                                all_fields=all_fields)

    def _do_load(self, stream, context, loaded_fields):
        """Load a structure list from the given stream.

        :param io.BufferedIOBase stream:
            A bit stream to read data from.
        :param context:
            Additional data to pass to this method. Subclasses must ignore
            anything they don't recognize.
        :param dict loaded_fields:
            A dictionary of the fields that have already been loaded. This is
            guaranteed to not be ``None``.

        :return: The deserialized data.
        :rtype: list
        """
        result = []
        while not self.halt_check(self, stream, result, context=context,
                                  loaded_fields=loaded_fields):
            result.append(
                self.component.load(stream, context=context,
                                    loaded_fields=loaded_fields)
            )

        return result


class Nested(Field):
    """Used to nest one struct inside of another.

    :param Type[binobj.structures.Struct] struct_class:
        The struct class to wrap as a field. Not an instance!
    """
    def __init__(self, struct_class, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.struct_class = struct_class

    def _do_dump(self, stream, data, context, all_fields):
        instance = self.struct_class(**data)
        return instance.to_stream(stream, context=context, all_fields=all_fields)

    def _do_load(self, stream, context, loaded_fields):
        return self.struct_class.from_stream(stream, context=context,
                                             loaded_fields=loaded_fields)


class Bytes(Field):
    """Raw binary data."""
    def _do_load(self, stream, context, loaded_fields):
        return self._read_exact_size(stream)

    def _do_dump(self, stream, data, context, all_fields):
        if not isinstance(data, (bytes, bytearray)):
            raise errors.UnserializableValueError(field=self, value=data)

        stream.write(data)


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
    :param bool signed:
        If ``True``, this field is a signed integer.

    .. note::

        Not all integer encodings allow signed integers.
    """
    def __init__(self, *, vli_format, max_bytes=None, **kwargs):
        super().__init__(**kwargs)

        if vli_format == varints.VarIntEncoding.VLQ and self.signed is True:
            raise errors.ConfigurationError(
                "Signed integers can't be encoded with VLQ. Either pass "
                "`signed=False` to __init__ or use an encoding that works for "
                "signed integers, like %s."
                % varints.VarIntEncoding.COMPACT_INDICES,
                field=self)

        encoding_functions = varints.INTEGER_ENCODING_MAP.get(vli_format)
        if encoding_functions is None:
            raise errors.ConfigurationError(
                'Invalid or unsupported integer encoding scheme: %r' % vli_format,
                field=self)

        self.vli_format = vli_format
        self.max_bytes = max_bytes
        self._encode_integer_fn = encoding_functions['encode']
        self._decode_integer_fn = encoding_functions['decode']

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

    :param int size:
        The field's size in *bytes*, not *characters*. For most text encodings
        these are the same, but encodings use multiple bytes per character.

    :param str encoding:
        The encoding to use for converting the string to and from bytes. Defaults
        to ``'latin-1'``.

    :param bytes pad:
        A single byte to use as padding for strings that are too short to fit
        into the field. If not given, strings that aren't exactly ``size`` bytes
        when encoded will trigger a :class:`~binobj.errors.ValueSizeError`.

    .. note ::

        The ``utf-8-sig``, ``utf-16``, and ``utf-32`` codecs add a byte order
        marker (BOM) at the beginning of the string, so you'll need to take those
        extra bytes into account when defining this field size. Alternatively,
        you can use the codecs' variants that don't add the BOM, such as
        ``utf-16-le`` or ``utf-16-be``.
    """
    def __init__(self, *, encoding='latin-1', pad_byte=None, **kwargs):
        super().__init__(**kwargs)

        if pad_byte is not None:
            if not isinstance(pad_byte, (bytes, bytearray)):
                raise TypeError('`pad_byte` must be a bytes-like object.')
            elif len(pad_byte) != 1:
                raise ValueError('`pad_byte` must be exactly one byte long.')

        self.encoding = encoding
        self.pad_byte = pad_byte

    # pylint: disable=unused-argument

    def _do_load(self, stream, context, loaded_fields):
        """Load a fixed-length string from a stream."""
        to_load = self._read_exact_size(stream)
        return to_load.decode(self.encoding)

    def _do_dump(self, stream, data, context, all_fields):
        """Dump a fixed-length string into the stream."""
        if self.size is None:
            raise errors.ConfigurationError(
                '`size` cannot be `None` on a fixed-length field.', field=self)

        stream.write(self._encode_and_resize(data))

    # pylint: enable=unused-argument

    def _encode_and_resize(self, string):
        """Encode a string and size it to this field.

        :param str string:
            The string to encode.

        :return: ``string`` encoded as ``size`` bytes.
        :rtype: bytes
        """
        to_dump = string.encode(self.encoding)

        if self.size is None:
            return to_dump

        size_diff = len(to_dump) - self.size
        if size_diff > 0:
            # String is too long.
            raise errors.ValueSizeError(field=self, value=to_dump)
        elif size_diff < 0:
            if self.pad_byte is None:
                # String is too short and we're not padding it.
                raise errors.ValueSizeError(field=self, value=to_dump)
            to_dump += self.pad_byte * -size_diff

        return to_dump


class StringZ(String):
    """A null-terminated string."""
    def _do_load(self, stream, context, loaded_fields):
        iterator = helpers.iter_bytes(stream, self.size)
        reader = codecs.iterdecode(iterator, self.encoding)
        result = io.StringIO()

        for char in reader:
            if char == '\0':
                return result.getvalue()
            result.write(char)

        # If we get out here then we hit EOF before getting to the null terminator.
        raise errors.DeserializationError(
            'Hit EOF before finding the trailing null.',
            field=self)

    def _do_dump(self, stream, data, context, all_fields):
        stream.write(self._encode_and_resize(data + '\0'))
