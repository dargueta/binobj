"""Definitions of all field types that can be used in structures."""


import abc
import codecs
import collections.abc
import functools
import io
import struct
import sys
import warnings

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
    :param validate:
        A callable or list of callables that validates a given value for this
        field. The callable(s) will always be passed the deserialized value, so
        a validator for an :class:`Integer` field will always be passed an
        :class:`int`, a :class:`String` validator will always be passed a
        :class:`str`, and so on.

    .. attribute:: index

        The zero-based index of the field in the struct.

        :type: int

    .. attribute:: offset

        The zero-based byte offset of the field in the struct. If the offset
        can't be computed (e.g. it's preceded by a variable-length field), this
        will be ``None``.

        :type: int

    .. attribute:: size

        The size of this object, in bytes. Builtin fields set this automatically
        if ``const`` is given but you'll need to override :meth:`_size_for_value`
        in custom fields.

        :type: int
    """
    def __init__(self, *, name=None, const=UNDEFINED, default=UNDEFINED,
                 discard=False, null_value=UNDEFINED, size=None, validate=()):
        self.const = const
        self.discard = discard
        self.null_value = null_value
        self._size = size

        if isinstance(validate, collections.Iterable):
            self.validators = [functools.partial(v, self) for v in validate]
        else:
            self.validators = [functools.partial(validate, self)]

        if default is UNDEFINED and const is not UNDEFINED:
            # If no default is given but ``const`` is, set the default value to
            # ``const``.
            self._default = const
        else:
            self._default = default

        # These attributes are typically set by the struct containing the field
        # after the field's instantiated.
        self.name = name        # type: str
        self.index = None       # type: int
        self.offset = None      # type: int
        self._compute_fn = None     # type: callable

    @property
    def size(self):
        """The size of this field, in bytes.

        :type: int
        """
        # Part of the _size_for_value() hack.
        if self._size is None and self.const is not UNDEFINED:
            self._size = self._size_for_value(self.const)
        return self._size

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
        self.name = name
        self.index = index
        self.offset = offset

    def compute_value_for_dump(self, all_values):
        """Calculate the value for this field upon dumping.

        :param dict all_values:
            The dictionary of all the field data that's about to be dumped.

        :return: The value the dumper will use for this field.

        :raise binobj.errors.MissingRequiredValueError:
            No value could be derived for this field. It's missing in the input
            data, there's no default defined, and it doesn't have a compute
            function defined either.
        """
        if self.name in all_values:
            return all_values[self.name]
        elif self._default is not UNDEFINED:
            return self.default
        elif self._compute_fn is not None:
            return self._compute_fn(self, all_values)

        raise errors.MissingRequiredValueError(field=self)

    def computes(self, method):
        """Decorator that marks a function as computing the value for a field.

        You can use this for automatically assigning values based on other fields.
        For example, suppose we have this struct::

            class MyStruct(Struct):
                n_numbers = UInt8()
                numbers = Array(UInt8(), count=n_numbers)

        This works great for loading, but when we're dumping we have to pass in a
        value for ``n_numbers`` explicitly. We can use the ``computes`` decorator
        to relieve us of that burden::

            class MyStruct(Struct):
                n_numbers = UInt8()
                numbers = Array(UInt8(), count=n_numbers)

                @n_numbers.computes
                def _assign_n_numbers(self, all_fields):
                    return len(all_fields['numbers'])

        Some usage notes:

        * The computing function will *not* be called if

          * A value is explicitly set for the field by the calling code.
          * The field has a ``default`` or ``const`` value.

        * Computed fields are executed in the order that the fields are dumped,
          so a computed field must *not* rely on the value of another computed
          field occurring after it.

        .. versionadded:: 0.3.0
        """
        if self._compute_fn:
            raise errors.ConfigurationError(
                "Cannot define two computing functions for field %r." % self,
                field=self)
        elif self.const is not UNDEFINED:
            raise errors.ConfigurationError(
                'Cannot set compute function for a const field.', field=self)
        self._compute_fn = method

    @property
    def allow_null(self):
        """Is ``None`` an acceptable value for this field?

        :type: bool
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

    def _size_for_value(self, value):   # pylint: disable=no-self-use,unused-argument
        """Return the size of the serialized value in bytes, or ``None`` if it
        can't be computed.

        This is an ugly hack for computing ``size`` properly when only ``const``
        is given. It's *HIGHLY DISCOURAGED* to implement this function in your
        own field subclasses.

        :param value:
            The value to serialize.

        :return:
            The size of ``value`` when serialized, in bytes. If the size cannot
            be computed, return ``None``.
        :rtype: int
        """
        return None

    def load(self, stream, context=None, loaded_fields=None):
        """Load data from the given stream.

        :param io.BufferedIOBase stream:
            The stream to load data from.
        :param context:
            Additional data to pass to this method. Subclasses must ignore
            anything they don't recognize.
        :param dict loaded_fields:
            A dictionary of the fields that have already been loaded. This is
            set automatically when a field is loaded by a
            :class:`~binobj.structures.Struct`.

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

        for validator in self.validators:
            validator(loaded_value)

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
            set automatically when a field is loaded by a
            :class:`~binobj.structures.Struct`.

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
            A dictionary of the fields about to be dumped. This is automatically
            set automatically by the field's containing
            :class:`~binobj.structures.Struct`.
        """
        if all_fields is None:
            all_fields = {}

        if data is DEFAULT:
            data = self.default
            if data in (UNDEFINED, DEFAULT):
                raise errors.MissingRequiredValueError(field=self)
        elif data is None:
            data = self._get_null_value()

        for validator in self.validators:
            validator(data)

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
            A dictionary of the fields about to be dumped. This is automatically
            set automatically by the field's containing
            :class:`~binobj.structures.Struct`.

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

        :raise UndefinedSizeError:
            The field cannot be read directly because it's of variable size.
        :raise UnexpectedEOFError: Not enough bytes were left in the stream.
        """
        offset = stream.tell()
        n_bytes = self.size

        if n_bytes is None:
            raise errors.UndefinedSizeError(field=self)

        data_read = stream.read(n_bytes)
        if len(data_read) < n_bytes:
            raise errors.UnexpectedEOFError(
                field=self, size=n_bytes, offset=offset)

        return data_read

    def __get__(self, instance, owner):
        if instance is None:
            return self
        elif self.name in instance.__values__:
            return instance.__values__[self.name]
        return self.compute_value_for_dump(instance)

    def __set__(self, instance, value):
        if self._compute_fn or self.const is not UNDEFINED:
            raise errors.ImmutableFieldError()

        for validator in self.validators:
            validator(value)
        instance.__values__[self.name] = value

    def __str__(self):
        return '%s(name=%r)' % (type(self).__name__, self.name)


class Array(Field):
    """An array of other serializable objects.

    :param Field component:
        The component this array is comprised of.
    :param count:
        Optional. Some way of indicating the number of elements in this array.
        The value for this argument can be one of the following:

        * An integer. The array always contains this many elements.
        * A :class:`Field` instance that must 1) be an integer; 2) occur before
          this array in the same struct.
        * A string naming a field fitting the above criteria. You'll need this
          if your size field's name is a Python keyword.

        .. versionadded:: 0.3.0

            ``count`` can now be a :class:`Field` or string.

    :param callable halt_check:
        A function taking five arguments. See :meth:`should_halt` for the
        default implementation. Subclasses can override this function if desired
        to avoid having to pass in a custom function every time.
    """
    def __init__(self, component, *, count=None, halt_check=None, **kwargs):
        super().__init__(**kwargs)
        self.component = component
        self.halt_check = halt_check or self.should_halt

        if count is None or (isinstance(count, (int, str, Field))
                             and not isinstance(count, bool)):
            # The isinstance bool check is needed because `bool` is a subclass
            # of `int`.
            self.count = count
        else:
            raise TypeError('`count` must be an integer, string, or a `Field`.')

    @staticmethod
    def should_halt(seq, stream, values, context, loaded_fields):    # pylint: disable=unused-argument
        """Determine if the deserializer should stop reading from the input.

        The default implementation does the following:

        - If the ``Array`` has an integer ``count``, it compares ``count``
          against the length of ``values``. If ``len(values)`` is equal to or
          more than ``count`` it'll return ``True`` (halt), ``False`` otherwise.
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
        elif isinstance(seq.count, Field):
            return loaded_fields[seq.count.name] <= len(values)
        elif isinstance(seq.count, str):
            # The number of fields in this array is a field that should already
            # have been loaded.
            if seq.count not in loaded_fields:
                # Instead of throwing a KeyError, we'll throw a more helpful
                # exception.
                raise errors.FieldReferenceError(
                    "%r is either not a field in this struct or hasn't been "
                    "loaded yet." % seq.count, field=seq.count)
            return loaded_fields[seq.count] <= len(values)

        # Else: count is None. Our only option is to check to see if we hit EOF.

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
        return instance.to_stream(stream, context)

    def _do_load(self, stream, context, loaded_fields):
        return self.struct_class.from_stream(stream, context)


class Union(Field):
    """A field that can be one of several different types of structs or fields.

    :param choices:
        One or more :class:`~binobj.structures.Struct` classes or :class:`Field`
        instances that can be used for loading and dumping.

    :param callable load_decider:
        A function that decides which :class:`~binobj.structures.Struct` class or
        :class:`Field` instance to use for loading the input. It must take four
        arguments:

        * ``stream``: The stream being loaded from.
        * ``classes``: A list of classes that can be used for loading.
        * ``context``: Additional data to pass directly to the loader selected
          from ``classes``.
        * ``loaded_fields``: A dictionary of the fields that have already been
          loaded. This is guaranteed to not be ``None``.

    :param callable dump_decider:
        A function that decides which :class:`~binobj.structures.Struct` class or
        :class:`Field` instance to use for dumping the given data. It must take
        four arguments:

        * ``data``: A dictionary containing the data to dump.
        * ``classes``: A list of classes that can be used for dumping.
        * ``context``: Additional data to pass directly to the dumper selected
          from ``classes``.
        * ``all_fields``: A dictionary of the fields about to be dumped. This is
          guaranteed to not be ``None``.

    .. versionadded:: 0.3.0

    Usage with Structs::

        def load_decider(stream, classes, context, loaded_fields):
            data_type_id = loaded_fields['data_type']
            return classes[data_type_id]

        def dump_decider(data, classes, context, all_fields):
            data_type_id = all_fields['data_type']
            return classes[data_type_id]

        class MyStruct(Struct):
            data_type = UInt8()
            data = Union(UserInfo, FileInfo, SystemInfo,
                         load_decider=load_decider, dump_decider=dump_decider)

    Usage with Fields::

        class FieldsUnionContainer(binobj.Struct):
            data_type = fields.UInt8()
            item = fields.Union(fields.StringZ(),
                                fields.UInt16(endian='little'),
                                load_decider=fields_load_decider,
                                dump_decider=fields_dump_decider)
    """
    def __init__(self, *choices, load_decider, dump_decider, **kwargs):
        super().__init__(**kwargs)
        if any(isinstance(c, type) and issubclass(c, Field) for c in choices):
            raise errors.ConfigurationError(
                'You must pass an instance of a Field, not a class.', field=self)

        self.choices = choices
        self.load_decider = load_decider
        self.dump_decider = dump_decider

    def _do_dump(self, stream, data, context, all_fields):
        dumper = self.dump_decider(data, self.choices, context, all_fields)
        if isinstance(dumper, Field):
            return dumper.dump(stream, data, context, all_fields)

        # Else: Dumper is not a Field instance, assume this is a Struct.
        return dumper(**data).to_stream(stream, context)

    def _do_load(self, stream, context, loaded_fields):
        loader = self.load_decider(stream, self.choices, context, loaded_fields)
        if isinstance(loader, Field):
            return loader.load(stream, context, loaded_fields)

        # Else: loader is not a Field instance, assume this is a Struct.
        return loader.from_stream(stream, context)


class Bytes(Field):
    """Raw binary data."""
    def _do_load(self, stream, context, loaded_fields):
        return self._read_exact_size(stream)

    def _do_dump(self, stream, data, context, all_fields):
        if self.const is not UNDEFINED:
            stream.write(self.const)
            return

        if not isinstance(data, (bytes, bytearray)):
            raise errors.UnserializableValueError(field=self, value=data)
        elif self.size is not None and len(data) != self.size:
            raise errors.ValueSizeError(field=self, value=data)

        stream.write(data)

    def _size_for_value(self, value):
        return len(value)


class Float(Field):
    """A floating-point number in IEEE-754:2008 interchange format.

    This is a base class and should not be used directly.

    :param str endian:
        The endianness to use to load/store the float. Either 'big' or 'little'.
        If not given, defaults to the system's native byte ordering as given by
        :data:`sys.byteorder`.
    """
    def __init__(self, *, format_string, endian=None, **kwargs):
        super().__init__(**kwargs)

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

    def _size_for_value(self, value):
        return struct.calcsize(self.format_string)


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

        .. versionadded:: 0.2.0

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
            raise errors.UndefinedSizeError(field=self)

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

    def _size_for_value(self, value):
        return len(value.encode(self.encoding))


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
