"""Stuff for serializing data."""

import abc
import collections
import functools
import io
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

    def __new__(mcs, name, bases, namespace, **kwargs):
        # TODO (dargueta): Need to get fields from the superclasses as well.
        namespace['__components__'] = collections.OrderedDict(
            (name, comp)
            for name, comp in namespace.items()
            if isinstance(comp, _SerializableBase)
        )

        instance = super().__new__(mcs, name, bases, namespace, **kwargs)
        offset = 0

        for i, (f_name, field) in enumerate(namespace['__components__'].items()):
            field.index = i
            field.name = f_name
            field.struct_class = weakref.proxy(instance)
            field.offset = offset

            if offset is not None:
                # pylint: disable=protected-access

                # Some fields don't have a fixed size, so `size` will be `None`.
                # After a variable-length field we can't calculate the offset,
                # so `offset` will be `None` for the rest of this struct.
                if field._n_bits is None:
                    offset = None
                else:
                    offset += field._n_bits

        return instance


def cast_bitstrings(func):
    """A decorator that converts all :class:`bytes` and :class:`bytearray`
    arguments into `bitstring.Bits`."""
    @functools.wraps(func)
    def _wrapper(*args, **kwargs):
        args = list(args)

        for index, value in enumerate(args):
            if isinstance(value, (bytes, bytearray)):
                args[index] = bitstring.Bits(bytes=value)

        for key, value in kwargs.items():
            if isinstance(value, (bytes, bytearray)):
                kwargs[key] = bitstring.Bits(bytes=value)

        return func(*args, **kwargs)
    return _wrapper


def cast_bitstreams(*, writable):
    """A decorator that converts all :class:`io.BytesIO` arguments to either a
    `bitstring.BitStream` or a `bitstring.ConstBitStream`.

    :param bool writable:
        If ``False``, all stream arguments will be read-only. If ``True``, all
        will be writeable.

    :rtype: callable
    """
    def decorator(func):
        @functools.wraps(func)
        def _wrapper(*args, **kwargs):
            args = list(args)

            for index, value in enumerate(args):
                if isinstance(value, io.BytesIO):
                    if writable:
                        args[index] = bitstring.BitStream()
                    else:
                        data = value.read()
                        args[index] = bitstring.ConstBitStream(bytes=data)

            for key, value in kwargs.items():
                if isinstance(value, io.BytesIO):
                    if writable:
                        kwargs[key] = bitstring.BitStream()
                    else:
                        data = value.read()
                        kwargs[key] = bitstring.ConstBitStream(bytes=data)
            return func(*args, **kwargs)
        return _wrapper
    return decorator


class Serializable(_SerializableBase, metaclass=SerializableMeta):
    """Base class providing basic loading and dumping methods."""
    def __init__(self, *, n_bytes=None, n_bits=None, **kwargs):
        if n_bytes is not None and n_bits is not None:
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

        #: A dictionary of default options for loading and dumping functions.
        #: Subclasses can override these, and they can also be overridden with
        #: arguments to ``__init__``.
        self.__options__ = {}   # type: dict

        # FIXME (dargueta): No way of inheriting options from parent classes. :(
        if hasattr(self, 'Options') and isinstance(self.Options, type):
            self.__options__.update({
                name: value
                for name, value in vars(self.Options).items()
                if not name.startswith('_')
            })

        self.__options__.update(kwargs)

        # Define some keys we're gonna need for sure if the caller hasn't done
        # so already.
        for key, value in _PREDEFINED_KWARGS.items():
            self.__options__.setdefault(key, value)

        self._hooks = collections.defaultdict(collections.OrderedDict)

    def dump(self, stream, data=DEFAULT, context=None):
        """Convert the given data into bytes and write it to ``stream``.

        :param stream:
            The stream to write the serialized data into. Can be either an
            :class:`io.BytesIO` stream or a :class:`bitstring.BitStream`.
        :param data:
            The data to dump. Can be omitted if this is a constant field.
        :param context:
            Additional data to pass to this method. Subclasses must ignore
            anything they don't recognize.
        """
        if data is None:
            stream.insert(self._get_null_value())
        else:
            return self._do_dump(stream, data, context)

    def _do_dump(self, stream, data, context):
        """Convert the given data into bytes and write it to ``stream``.

        :param bitstring.BitStream stream:
            The bit stream to write the serialized data into.
        :param data:
            The data to dump. Guaranteed to not be ``None``.
        :param context:
            Additional data to pass to this method. Subclasses must ignore
            anything they don't recognize.
        """
        if isinstance(data, (bytes, bytearray)):
            stream.insert(data)
        else:
            raise errors.UnserializableValueError(
                reason='Unhandled data type: ' + type(data).__name__,
                field=self, value=data)

    @cast_bitstrings
    def dumps(self, data=DEFAULT, context=None):
        """Convert the given data into bytes.

        :param data:
            The data to dump. Can be omitted if this is a constant field.
        :param context:
            Additional data to pass to this method. Subclasses must ignore
            anything they don't recognize.

        :return: The serialized data, padded to the nearest byte.
        :rtype: bytes
        """
        stream = bitstring.BitStream()
        self.dump(stream, data, context)
        return stream.tobytes()

    @cast_bitstreams(writable=False)
    def load(self, stream, context=None):
        """Load data from the given stream.

        :param stream:
            The stream to load data from. Can be either an :class:`io.BytesIO`
            stream or a :class:`bitstring.ConstBitStream`.
        :param context:
            Additional data to pass to this method. Subclasses must ignore
            anything they don't recognize.

        :return: The deserialized data.
        """
        loaded_value = self._do_load(stream, context)
        if loaded_value == self.__options__['null_value']:
            return None
        return loaded_value

    @abc.abstractmethod
    def _do_load(self, stream, context):
        """Load from the given stream.

        :param bitstring.ConstBitStream stream:
            A stream to read data from.
        :param context:
            Additional data passed to :meth:`load`. Subclasses must ignore
            anything they don't recognize.

        :return: The deserialized data.
        """

    @cast_bitstrings
    def loads(self, data, context=None, exact=True):
        """Load from the given byte string.

        :param data:
            A bytes-like object to get the data from, either a :class:`bytes`,
            :class:`bytearray`, or :class:`bitstring.Bits`.
        :param context:
            Additional data to pass to this method. Subclasses must ignore
            anything they don't recognize.
        :param bool exact:
            ``data`` must contain exactly the number of bits required. If not
            all the bits in ``data`` were used when reading the struct, throw an
            exception.

        :return: The deserialized data.
        """
        stream = bitstring.ConstBitStream(data)
        loaded_data = self.load(stream, context)

        if exact and (stream.pos < stream.length - 1):
            # TODO (dargueta): Better error message.
            raise errors.ExtraneousDataError(
                'Expected to read %d bits, read %d.'
                % (stream.length - 1, stream.pos))
        return loaded_data

    def before_load(self, method):
        """Decorator that marks a method for execution before this object is
        loaded.

        The method must take the following arguments:

        - ``stream``: The stream the object is being loaded from.
        - ``loaded_objects``: An :class:`~collections.OrderedDict` mapping all
           of the objects read so far in the containing
           :class:`~binobj.structures.Struct`, :class:`~binobj.structures.Union`,
           etc.
        - ``context``: The context object passed to the containing object's
          :meth:`load` method.

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
           of the objects read so far in the containing
           :class:`~binobj.structures.Struct`, :class:`~binobj.structures.Union`,
           etc. The current object is included in this dict.
        - ``value``: The value of this object that was just read from the stream.
          This is provided mainly for convenience since it's also accessible in
          the ``loaded_objects`` dictionary.
        - ``context``: The context object passed to the containing object's
          :meth:`load` method.

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
        :rtype: bitstring.Bits
        """
        if not self.__options__['allow_null']:
            raise errors.UnserializableValueError(
                reason='`None` is not an acceptable value for %s.' % self,
                field=self,
                value=None)

        null_value = self.__options__['null_value']
        if null_value is not DEFAULT:
            return null_value

        # User wants us to define the null value for them.
        if self._n_bits is None:
            raise errors.UnserializableValueError(
                reason="Can't guess appropriate serialization of `None` for %s "
                       "because it has no fixed size." % self,
                field=self,
                value=None)

        return bitstring.Bits('0b' + ('0' * self._n_bits))

    def _read_exact_size(self, stream):
        """Read exactly the number of bits this object takes up or crash.

        :param bitstring.ConstBitStream stream: The stream to read from.

        :return: Exactly ``self.n_bits`` bits are read from the stream.
        :rtype: bitstring.Bits

        :raise UnexpectedEOFError: Not enough bits were left in the stream.
        """
        offset = stream.pos

        if self._n_bits is None:
            raise errors.VariableSizedFieldError(field=self, offset=offset)

        n_bits = self._n_bits

        try:
            return stream.read(n_bits)
        except bitstring.ReadError:
            raise errors.UnexpectedEOFError(
                field=self, size=self._n_bits, offset=offset)


class SerializableScalar(Serializable):
    """A serialization class for single values."""
    # TODO (dargueta): I feel like I'm supposed to be doing something here.


class SerializableContainer(Serializable):
    """A serialization class for container-like objects.

    :param list components:
        Optional. A list of :class:`Serializable` objects to use for this
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
        if components:
            self._components = components.copy()
        elif self.__components__:
            self._components = self.__components__.copy()
        else:
            raise errors.FieldConfigurationError(
                'Container has no defined components. You must define them at '
                'the class level with `__components__`, or pass them to the '
                'constructor in the `components` keyword argument.',
                field=self)

        super().__init__(**kwargs)

    def _do_dump(self, stream, data, context):
        """Convert the given data into bytes and write it to ``stream``.

        :param bitstring.BitStream stream:
            A stream to write the serialized data into.
        :param dict data:
            The data to dump.
        :param context:
            Additional data to pass to the :meth:`dump` function.
        """
        given_keys = set(data.keys())
        expected_keys = set(self._components.keys())
        extra_keys = given_keys - expected_keys
        if extra_keys:
            raise errors.UnexpectedValueError(struct=self, name=extra_keys)

        for name, component in self._components.items():
            value = data.get(name, UNDEFINED)

            if value is UNDEFINED:
                # Caller didn't pass a value for this component. If a default
                # value is defined, use it. Otherwise, crash.
                default = component.__options__['default']
                if default is UNDEFINED:
                    raise errors.MissingRequiredValueError(field=component)
                value = default

            component.dump(stream, value, context)

    def _do_load(self, stream, context=None):
        """Load a structure from the given byte stream.

        :param bitstring.ConstBitStream stream:
            A bit stream to read data from.
        :param context:
            Additional data to pass to the deserialization function. Subclasses
            must ignore anything they don't recognize.

        :return: The deserialized data.
        :rtype: collections.OrderedDict
        """
        result = collections.OrderedDict()
        for name, component in self._components.items():
            value = component.load(stream, context)
            if not component.discard:
                result[name] = value

        return result

    @cast_bitstreams(writable=False)
    def partial_load(self, stream, last_field=None, context=None):
        """Partially load this object, either until EOF or the named field.

        All fields up to and including the field named in ``last_field`` will be
        loaded from ``stream``.

        If ``last_field`` isn't given, as many complete fields as possible will
        be loaded from ``stream``. Any partially loaded fields will be discarded
        and the stream pointer will be reset to the end of the last complete
        field read.

        :param bitstring.ConstBitStream stream:
            The stream to load from.
        :param str last_field:
            The name of the last field to load in the object. If given, enough
            bytes for this and all previous fields *must* be present in the
            stream.
        :param context:
            Any object containing extra information to pass to the fields'
            :meth:`load` method.

        :return: The deserialized data.
        :rtype: collections.OrderedDict
        """
        if last_field is not None and last_field not in self._components:
            raise ValueError(
                "%s doesn't have a field named %r." % (self, last_field))

        result = collections.OrderedDict()
        for field in self._components.values():
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

    @cast_bitstreams(writable=True)
    def partial_dump(self, stream, data, last_field=None, context=None):
        """Partially dump the object, up to and including the last named field.

        All fields up to and including the field named in ``last_field`` will be
        serialized.

        If ``last_field`` isn't given, as many fields will be serialized as
        possible up to the first missing one.

        :param bitstring.BitStream stream:
            The stream to dump into.
        :param dict data:
            The data to dump.
        :param str last_field:
            The name of the last field in the object to dump.
        :param context:
            Any object containing extra information to pass to the fields'
            :meth:`load` methods.
        """
        given_keys = set(data.keys())
        expected_keys = set(self._components.keys())
        extra_keys = given_keys - expected_keys
        if extra_keys:
            raise errors.UnexpectedValueError(struct=self, name=extra_keys)

        for field in self._components.values():
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
            field.dump(stream, value, context)

            if field.name == last_field:
                return


class SerializableSequence(Serializable):
    """A serialization class for objects that're sequences of other objects."""
    __component__ = None    # type: Serializable

    def __init__(self, *, component=None, count=None, **kwargs):
        self._component = component or self.__component__
        if self._component is None:
            raise errors.FieldConfigurationError(
                'List has no defined component type. You must define one at '
                'the class level with `__component__`, or pass it to the '
                'constructor in the `component` keyword argument.',
                field=self)

        self.count = count
        super().__init__(**kwargs)

    def _should_halt(self, stream, loaded, context):    # pylint: disable=unused-argument
        """Determine if the deserializer should stop reading from the input.

        The default implementation does the following:

        - If the object has an integer attribute called ``count``, it compares
          ``count`` against the length of ``loaded``. If ``len(loaded)`` is less
          than ``count`` it'll return ``True`` (halt), ``False`` otherwise.
        - If the object *doesn't* have an attribute called ``count``, or
          ``count`` isn't an integer, the function returns ``True`` if there's
          any data left in the stream.

        :param bitstring.ConstBitStream stream:
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
        if isinstance(self.count, int):
            return self.count <= len(loaded)

        try:
            stream.peek(1)
        except bitstring.ReadError:
            return True
        return False

    def _do_dump(self, stream, data, context):
        """Convert the given data into bytes and write it to ``stream``.

        :param bitstring.BitStream stream:
            A bit stream to write the serialized data into.
        :param list data:
            The data to dump.
        :param context:
            Additional data to pass to this method. Subclasses must ignore
            anything they don't recognize.
        """
        for value in data:
            self._component.dump(stream, value, context)

    def _do_load(self, stream, context=None):
        """Load a structure list from the given stream.

        :param bitstring.ConstBitStream stream:
            A bit stream to read data from.
        :param context:
            Additional data to pass to this method. Subclasses must ignore
            anything they don't recognize.

        :return: The deserialized data.
        :rtype: list
        """
        result = []
        while not self._should_halt(stream, result, context):
            result.append(self._component.load(stream, context))

        return result
