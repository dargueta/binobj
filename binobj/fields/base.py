"""Base classes and definitions common to all Fields."""

import abc
import collections
import functools
import io

from binobj import errors


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
