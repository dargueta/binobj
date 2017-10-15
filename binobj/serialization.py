"""Stuff for serializing data."""

import abc
import collections
import copy
import weakref

import bitstring

from binobj import errors


class _NamedSentinel:   # pylint: disable=too-few-public-methods
    """Hack class for creating sentinel values that show their name in repr."""
    def __init__(self, name):
        self.__name = name

    def __repr__(self):
        return self.__name


#: A sentinel value used to indicate that a setting or field is undefined.
UNDEFINED = _NamedSentinel('UNDEFINED')

#: A sentinel value used to indicate that the default value of a setting should
#: be used. We need this because sometimes ``None`` is a valid value for that
#: setting.
DEFAULT = _NamedSentinel('DEFAULT')

#: A special return value that tells the loading or dumping function to stop.
HALT = _NamedSentinel('HALT')


_PREDEFINED_KWARGS = {
    'allow_null': True,
    'default': UNDEFINED,
    'null_value': DEFAULT,
}


class _SerializableBase:    # pylint: disable=too-few-public-methods
    """Ignore this.

    This empty base class is a hack around the circular dependency that would
    arise between `SerializableMeta` and `Serializable` since the metaclass
    needs to know what fields in the client class are serializable, but
    `Serializable` needs `SerializableMeta`.

    There's gotta be a way around this.
    """


class SerializableMeta(abc.ABCMeta):
    """Base metaclass for all structure-like things."""
    @classmethod
    def __prepare__(mcs, name, bases):      # pylint: disable=unused-argument
        return collections.OrderedDict()

    def __new__(mcs, name, bases, namespace):
        # TODO (dargueta): Need to get fields from the superclasses as well.
        namespace['__components__'] = collections.OrderedDict(
            (name, comp)
            for name, comp in namespace.items()
            if isinstance(comp, _SerializableBase)
        )

        instance = super().__new__(mcs, name, bases, namespace)
        offset = 0

        for i, (f_name, field) in enumerate(namespace['__components__'].items()):
            field.index = i
            field.name = f_name
            field.struct_class = weakref.proxy(instance)
            field.offset = offset

            if offset is not None:
                # Some fields don't have a fixed size, so `size` will be `None`.
                # After a variable-length field we can't calculate the offset,
                # so `offset` will be `None` for the rest of this struct.
                if field.n_bits is None:
                    offset = None
                else:
                    offset += field.n_bits

        return instance


class Serializable(metaclass=SerializableMeta):
    """Base class providing basic loading and dumping methods."""
    #: A dictionary of default options for loading and dumping functions.
    #: Subclasses can override these, and they can also be overridden with
    #: arguments to ``__init__``.
    __options__ = None     # type: dict

    def __init__(self, *, n_bytes=None, n_bits=None, **kwargs):
        if n_bytes and n_bits:
            raise errors.FieldConfigurationError(
                "Only one of `n_bytes` and `n_bits` can be defined for an "
                "object. Got n_bytes=%r and n_bits=%r." % (n_bytes, n_bits),
                field=self)

        if n_bytes:
            self._n_bytes = n_bytes
            self._n_bits = n_bytes * 8
        elif n_bits and n_bits % 8 == 0:
            self._n_bits = n_bits
            self._n_bytes = n_bits // 8
        else:
            self._n_bits = n_bits
            self._n_bytes = n_bytes

        if self.__options__ is not None:
            self.__options__ = copy.deepcopy(self.__options__)
            self.__options__.update(kwargs)
        else:
            self.__options__ = kwargs

        for key, value in _PREDEFINED_KWARGS.items():
            self.__options__.setdefault(key, value)

        self._hooks = collections.defaultdict(collections.OrderedDict)
        self._references_to_this = {}
        self._references_to_others = {}

    @abc.abstractmethod
    def dump(self, data, stream, context=None):
        """Convert the given data into bytes and write it to ``stream``.

        :param data:
            The data to dump.
        :param bitstring.BitStream stream:
            The bit stream to write the serialized data into.
        :param context:
            Additional data to pass to this method. Subclasses must ignore
            anything they don't recognize.
        """

    def dumps(self, data, context=None):
        """Convert the given data into bytes.

        :param data:
            The data to dump.
        :param context:
            Additional data to pass to this method. Subclasses must ignore
            anything they don't recognize.

        :return: The serialized data, padded to the nearest byte.
        :rtype: bytes
        """
        stream = bitstring.BitStream()
        self.dump(data, stream, context)
        return stream.tobytes()

    @abc.abstractmethod
    def load(self, stream, context=None):
        """Load a structure from the given byte stream.

        :param bitstring.BitStream stream:
            A bit stream to read data from.
        :param context:
            Additional data to pass to this method. Subclasses must ignore
            anything they don't recognize.

        :return: The deserialized data.
        :rtype: object
        """

    def loads(self, byte_string, context=None, exact=False):
        """Load a structure from the given byte stream.

        :param byte_string:
            A bytes-like object to get the data from, either `bytes` or a
            `bytearray`.
        :param context:
            Additional data to pass to this method. Subclasses must ignore
            anything they don't recognize.
        :param bool exact:
            ``byte_string`` must contain exactly the number of bytes required.
            If not all the bytes in ``byte_string`` were used when reading the
            struct, throw an exception.

        :return: The deserialized data.
        :rtype: object
        """
        stream = bitstring.BitStream(bytes=byte_string)
        loaded_data = self.load(stream, context)

        if exact and (stream.pos < stream.length - 1):
            # TODO (dargueta): Better error message.
            raise errors.ExtraneousDataError()
        return loaded_data

    def before_load(self, method):
        """Decorator that marks a method for execution before this object is
        loaded.

        The method must take the following arguments:

        - ``stream``: The stream the object is being loaded from.
        - ``loaded_objects``: An :class:`~collections.OrderedDict` mapping all
           of the objects read so far in the containing :class:`Struct`,
           :class:`Union`, etc.
        - ``context``: The context object passed to the containing object's
          ``load()`` method.

        Usage::

            class MyStruct(Struct):
                my_field = Integer(n_bytes=3)

                @my_field.before_load
                def do_something(self, stream, loaded_objects, context):
                    ...
        """
        self._hooks['before_load'][method.__name__] = method
        return method

    def after_load(self, method):
        """Decorator that marks a method for execution after this object is
        loaded.

        The method must take the following arguments:

        - ``stream``: The stream the object is being loaded from.
        - ``loaded_objects``: An :class:`~collections.OrderedDict` mapping all
           of the objects read so far in the containing :class:`Struct`,
           :class:`Union`, etc. The current object is included in this dict.
        - ``value``: The value of this object that was just read from the stream.
          This is provided mainly for convenience since it's also accessible in
          the ``loaded_objects`` dictionary.
        - ``context``: The context object passed to the containing object's
          ``load()`` method.

        Usage::

            class MyStruct(Struct):
                my_field = Integer(n_bytes=3)

                @my_field.after_load
                def do_something(self, stream, value, loaded_objects, context):
                    ...
        """
        self._hooks['after_load'][method.__name__] = method
        return method

    def before_dump(self, method):
        """Decorator that marks a method for execution before this object is
        dumped."""
        self._hooks['before_dump'][method.__name__] = method
        return method

    def after_dump(self, method):
        """Decorator that marks a method for execution after this object is
        dumped."""
        self._hooks['after_dump'][method.__name__] = method
        return method

    def _get_null_value(self):
        """Return the serialized value for ``None``.

        We need this function because there's some logic involved in determining
        if ``None`` is a legal value, and guessing the serialization if no
        default value is provided.

        :return: The serialized form of ``None`` for this field.
        :rtype: bytes
        """
        if not self.__options__['allow_null']:
            raise errors.UnserializableValueError(
                reason='`None` is not an acceptable value for %s.' % self,
                field=self,
                value=None)

        null_value = self.__options__['null_value']

        if null_value is DEFAULT:
            # User wants us to define the null value for them.
            if self._n_bits is None:
                raise errors.UnserializableValueError(
                    reason="Can't guess appropriate serialization of `None` "
                           "for %s because it has no fixed size." % self,
                    field=self,
                    value=None)
            null_value = '0b' + ('0' * self._n_bits)

        return null_value

    def _read_exact_size(self, stream):
        """Read exactly the number of bits this object takes up or crash.

        :param bitstring.BitStream stream: The stream to read from.

        :return: Exactly ``self.n_bits`` bits are read from the stream.
        :rtype: bitstring.Bits

        :raise UnexpectedEOFError: Not enough bits were left in the stream.
        """
        offset = stream.pos

        if self._n_bits is None:
            raise errors.VariableSizedFieldError(field=self, offset=offset)

        try:
            return stream.read(self._n_bits)
        except bitstring.ReadError:
            raise errors.UnexpectedEOFError(
                field=self, size=self._n_bits, offset=offset)


class SerializableScalar(Serializable):
    """A serialization class for single values."""
    def load(self, stream, context=None):
        """Load a value from a byte stream.

        :param bitstring.BitStream stream:
            The stream to read the next value from.
        :param context:
            Optional. Additional data passed by the caller that can be used by
            this function.

        :return: The deserialized value.
        """
        loaded_value = stream.read(self._n_bits)
        if loaded_value == self.__options__['null_value']:
            return None
        return loaded_value

    def dump(self, data, stream, context=None):
        """Write this field into a bit stream.

        :param data:
            The value to serialize.
        :param bitstring.BitStream stream:
            The stream to write the serialized representation of ``value`` into.
        :param context:
            Optional. Additional data passed by the caller that can be used by
            this function.
        """
        if data is None:
            stream.insert(self._get_null_value())
        elif isinstance(data, bytes):
            stream.insert(data)
        else:
            raise errors.UnserializableValueError(
                reason='Unhandled data type: ' + type(data).__name__,
                field=self, value=data)


class SerializableContainer(Serializable):
    """A serialization mixin class for container-like objects.

    :param list components:
        Optional. A list of serializable fields, structs, etc. to use for this
        container. Completely overrides any class-level declared fields (stored
        in ``__components__``).

        Really you should only be using this argument if you need to dynamically
        declare a struct.
    """
    #: An :class:`~collections.OrderedDict` of the serializables comprising the
    #: container.
    #:
    #: This is set by the metaclass but defined here for documentation purposes.
    __components__ = None   # type: collections.OrderedDict

    def __init__(self, *, components=None, **kwargs):
        self.__components__ = components or self.__components__
        if self.__components__ is None:
            raise errors.FieldConfigurationError(
                'Container has no defined components. You must define them at '
                'the class level with `__components__`, or pass them to the '
                'constructor in the `components` keyword argument.',
                field=self)

        super().__init__(**kwargs)

    def dump(self, data, stream, context=None):
        """Convert the given data into bytes and write it to ``stream``.

        :param dict data:
            The data to dump.
        :param bitstring.BitStream stream:
            A stream to write the serialized data into.
        :param context:
            Additional data to pass to the ``dump()`` function.
        """
        given_keys = set(data.keys())
        expected_keys = set(self.__components__.keys())
        extra_keys = given_keys - expected_keys
        if extra_keys:
            raise errors.UnexpectedValueError(struct=self, name=extra_keys)

        for name, component in self.__components__.items():
            value = data.get(name, UNDEFINED)

            if value is UNDEFINED:
                # Caller didn't pass a value for this component. If a default
                # value is defined, use it. Otherwise, crash.
                default = component.__options__['default']
                if default is UNDEFINED:
                    raise errors.MissingRequiredValueError(field=component)
                value = default

            component.dump(value, stream, context)

    def load(self, stream, context=None):
        """Load a structure from the given byte stream.

        :param bitstring.BitStream stream:
            A bit stream to read data from.
        :param context:
            Additional data to pass to the deserialization function. Subclasses
            must ignore anything they don't recognize.

        :return: The deserialized data.
        :rtype: collections.OrderedDict
        """
        result = collections.OrderedDict()
        for name, component in self.__components__.items():
            result[name] = component.load(stream, context)

        return result

    def partial_load(self, stream, last_field=None, context=None):
        """Partially load this object, either until EOF or the named field.

        All fields up to and including the field named in ``last_field`` will be
        loaded from ``stream``.

        If ``last_field`` isn't given, as many complete fields as possible will
        be loaded from ``stream``. Any partially loaded fields will be discarded
        and the stream pointer will be reset to the end of the last complete
        field read.

        :param bitstring.BitStream stream:
            The stream to load from.
        :param str last_field:
            The name of the last field to load in the object. If given, enough
            bytes for this and all previous fields *must* be present in the
            stream.
        :param context:
            Any object containing extra information to pass to the fields'
            ``load()`` method.

        :return: The deserialized data.
        :rtype: collections.OrderedDict
        """
        if last_field is not None and last_field not in self.__components__:
            raise ValueError(
                "%s doesn't have a field named %r." % (self, last_field))

        result = collections.OrderedDict()
        for field in self.__components__.values():
            offset = stream.pos

            try:
                value = field.load(stream, context)
            except errors.UnexpectedEOFError:
                if last_field is not None:
                    # Hit EOF before we read all the fields we were supposed to.
                    raise

                # Hit EOF in the middle of reading a field. Since the caller
                # didn't specify how far we should read, this isn't an error. Go
                # back to the beginning of this field and return.
                stream.pos = offset
                return result

            if not field.discard:
                result[field.name] = value

            if field.name == last_field:
                return result

        return result

    def partial_dump(self, data, stream, last_field=None, context=None):
        """Partially dump the object, up to and including the last named field.

        All fields up to and including the field named in ``last_field`` will be
        serialized.

        If ``last_field`` isn't given, as many fields will be serialized as
        possible up to the first missing one.

        :param dict data:
            The data to dump.
        :param bitstring.BitStream stream:
            The stream to dump into.
        :param str last_field:
            The name of the last field in the object to dump.
        :param context:
            Any object containing extra information to pass to the fields'
            ``load()`` methods.
        """
        given_keys = set(data.keys())
        expected_keys = set(self.__components__.keys())
        extra_keys = given_keys - expected_keys
        if extra_keys:
            raise errors.UnexpectedValueError(struct=self, name=extra_keys)

        for field in self.__components__.values():
            if field.name not in data:
                # Field is missing from the dump data. If the caller wants us to
                # dump only the fields that're defined, we can bail out now.
                if last_field is None:
                    return
                elif field.required:
                    # Caller wants us to dump up to and including ``last_field``
                    # so we need to crash.
                    raise errors.MissingRequiredValueError(field=field)

            value = data.get(field.name, field.__options__['default'])
            field.dump(value, stream, context)

            if field.name == last_field:
                return


class SerializableSequence(Serializable):
    """A serialization class for objects that're sequences of other objects."""
    __component__ = None    # type: Serializable

    def __init__(self, *, component=None, count=None, **kwargs):
        self.__component__ = component or self.__component__
        if self.__component__ is None:
            raise errors.FieldConfigurationError(
                'List has no defined component type. You must define one at '
                'the class level with `__component__`, or pass it to the '
                'constructor in the `component` keyword argument.',
                field=self)

        self.count = count
        super().__init__(component=component, **kwargs)

    def _should_halt(self, stream, loaded, context):    # pylint: disable=unused-argument
        """Determine if the deserializer should stop reading from the input.

        The default implementation does the following:

        - If the object has an integer attribute called ``count``, it compares
          ``count`` against the length of ``loaded``. If ``len(loaded)`` is less
          than ``count`` it'll return ``True`` (halt), ``False`` otherwise.
        - If the object *doesn't* have an attribute called ``count``, or
          ``count`` isn't an integer, the function returns ``True`` if there's
          any data left in the stream.

        :param bitstring.BitStream stream:
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
        # TODO (dargueta): Handle ValueOf references here somehow.
        if isinstance(self.count, int):
            return self.count <= len(loaded)

        try:
            stream.peek(1)
        except bitstring.ReadError:
            return True
        return False

    def dump(self, data, stream, context=None):
        """Convert the given data into bytes and write it to ``stream``.

        :param list data:
            The data to dump.
        :param bitstring.BitStream stream:
            A bit stream to write the serialized data into.
        :param context:
            Additional data to pass to this method. Subclasses must ignore
            anything they don't recognize.
        """
        for value in data:
            self.__component__.dump(value, stream, context)

    def load(self, stream, context=None):
        """Load a structure list from the given stream.

        :param bitstring.BitStream stream:
            A bit stream to read data from.
        :param context:
            Additional data to pass to this method. Subclasses must ignore
            anything they don't recognize.

        :return: The deserialized data.
        :rtype: list
        """
        result = []
        while not self._should_halt(stream, result, context):
            result.append(self.__component__.load(stream, context))

        return result
