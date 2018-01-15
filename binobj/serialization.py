"""Base classes for representing objects that can be loaded and stored as binary
data."""

import abc
import collections
import collections.abc
import copy
import io

from binobj import errors
from binobj import helpers


class _NamedSentinel:
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

    def __reduce__(self):
        return _NamedSentinel.get_sentinel, (self.name,)

    def __repr__(self):
        return 'Sentinel(%r)' % self.name


#: A sentinel value used to indicate that a setting or field is undefined.
UNDEFINED = _NamedSentinel.get_sentinel('UNDEFINED')


#: A sentinel value used to indicate that the default value of a setting should
#: be used. We need this because sometimes ``None`` is a valid value for that
#: setting.
DEFAULT = _NamedSentinel.get_sentinel('DEFAULT')


#: A read-only dictionary of predefined options for serializable objects.
_DEFAULT_OPTIONS = {
    'allow_null': True,
    'const': UNDEFINED,
    'default': UNDEFINED,
    'null_value': DEFAULT,
}


def gather_options_for_class(klass):
    """Build a dictionary of an object's settings, including values defined in
    parent classes.

    :param type klass:
        A class object (not an instance) that we want to get the options for.
        The class must have an internal class named ``Options``.

    :return: A dictionary of the class' defined options, plus a few defaults.
    :rtype: dict
    """
    dct = copy.deepcopy(_DEFAULT_OPTIONS)
    return _r_gather_options_for_class(klass, dct, set())


def _r_gather_options_for_class(klass, options, seen):
    """Helper method for :func:`gather_options_from_class`.

    :param type klass:
    :param dict options:
    :param set seen:

    :return: The class' options, including the ones defined in its superclasses.
    :rtype: dict
    """
    seen.add(klass)

    # Determine all the options defined in the parent classes
    for parent_class in reversed(klass.__bases__):
        if parent_class not in seen:
            _r_gather_options_for_class(parent_class, options, seen)
        seen.add(parent_class)

    if hasattr(klass, 'Options') and isinstance(klass.Options, type):
        options_to_copy = {
            name: value
            for name, value in vars(klass.Options).items()
            if not name.startswith('_')
        }

        options.update(copy.deepcopy(options_to_copy))

    return options


class Serializable:
    """Base class providing basic loading and dumping methods.

    .. attribute:: __options__

        A dictionary of options used by the loading and dumping methods.
        Subclasses can override these options, and they can also be overridden
        on a per-instance basis with keyword arguments passed to the constructor.
        Keyword arguments not recognized by a constructor will be put in here.

        :type: dict

    .. attribute:: size

        The size of this object, in bytes.

        :type: int
    """
    def __init__(self, *, size=None, **kwargs):
        self.size = size
        self.__options__ = gather_options_for_class(type(self))
        self.__options__.update(kwargs)

    def dump(self, stream, data=DEFAULT, context=None):
        """Convert the given data into bytes and write it to ``stream``.

        :param io.BytesIO stream:
            The stream to write the serialized data into.
        :param data:
            The data to dump. Can be omitted only if this is a constant field,
            i.e. ``__options__['const']`` is not :data:`UNDEFINED`.
        :param context:
            Additional data to pass to this method. Subclasses must ignore
            anything they don't recognize.
        """
        if data is None:
            stream.write(self._get_null_value())
        else:
            self._do_dump(stream, data, context)

    def _do_dump(self, stream, data, context):  # pylint: disable=unused-argument
        """Convert the given data into bytes and write it to ``stream``.

        :param io.BytesIO stream:
            The stream to write the serialized data into.
        :param data:
            The data to dump. Guaranteed to not be ``None``.
        :param context:
            Additional data to pass to this method. Subclasses must ignore
            anything they don't recognize.
        """
        if isinstance(data, (bytes, bytearray)):
            stream.write(data)
        elif data is DEFAULT or data is UNDEFINED:
            stream.write(self._get_default_value())
        else:
            raise errors.UnserializableValueError(
                reason='Unhandled data type: ' + type(data).__name__,
                field=self, value=data)

    def dumps(self, data=DEFAULT, context=None):
        """Convert the given data into bytes.

        :param data:
            The data to dump. Can be omitted only if this is a constant field,
            i.e. ``__options__['const']`` is not :data:`UNDEFINED`.
        :param context:
            Additional data to pass to this method. Subclasses must ignore
            anything they don't recognize.

        :return: The serialized data.
        :rtype: bytes
        """
        stream = io.BytesIO()
        self.dump(stream, data, context)
        return stream.getvalue()

    def load(self, stream, context=None):
        """Load data from the given stream.

        :param io.BytesIO stream:
            The stream to load data from.
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

        :param io.BytesIO stream:
            A stream to read data from.
        :param context:
            Additional data passed to :meth:`load`. Subclasses must ignore
            anything they don't recognize.

        :return: The deserialized data.
        """

    def loads(self, data, context=None, exact=True):
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

        :return: The deserialized data.
        """
        stream = io.BytesIO(data)
        loaded_data = self.load(stream, context)

        if exact and (stream.tell() < len(data)):
            # TODO (dargueta): Better error message.
            raise errors.ExtraneousDataError(
                'Expected to read %d bytes, read %d.'
                % (stream.tell(), len(data)))
        return loaded_data

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
        if null_value is not DEFAULT:
            return null_value

        # User wants us to define the null value for them.
        if self.size is None:
            raise errors.UnserializableValueError(
                reason="Can't guess appropriate serialization of `None` for %s "
                       "because it has no fixed size." % self,
                field=self,
                value=None)

        return bytes([0] * self.size)

    def _read_exact_size(self, stream):
        """Read exactly the number of bytes this object takes up or crash.

        :param io.BytesIO stream: The stream to read from.

        :return: Exactly ``self.size`` bytes are read from the stream.
        :rtype: bytes

        :raise VariableSizedFieldError:
            The field cannot be read directly because it's of variable size.
        :raise UnexpectedEOFError: Not enough bytes were left in the stream.
        """
        offset = stream.tell()

        if self.size is None:
            raise errors.VariableSizedFieldError(field=self, offset=offset)

        n_bytes = self.size
        data_read = stream.read(n_bytes)

        if len(data_read) < n_bytes:
            raise errors.UnexpectedEOFError(
                field=self, size=self.size, offset=offset)

        return data_read

    def _get_default_value(self):
        const = self.__options__.get('const', UNDEFINED)
        if const is not UNDEFINED:
            return const

        default = self.__options__.get('default', UNDEFINED)
        if default is not UNDEFINED:
            return default

        return UNDEFINED


class SerializableContainerMeta(abc.ABCMeta):
    """The metaclass for all serializable objects composed of other serializable
    objects.

    It defines the ``__components__`` class variable and sets some values on the
    :class:`Serializable` components such as the name and index.
    """
    @classmethod
    def __prepare__(mcs, name, bases):      # pylint: disable=unused-argument
        return collections.OrderedDict()

    def __new__(mcs, name, bases, namespace, **kwargs):
        # TODO (dargueta): Need to get fields from the superclasses as well.
        namespace['__components__'] = collections.OrderedDict(
            (name, comp)
            for name, comp in namespace.items()
            if isinstance(comp, Serializable)
        )

        class_object = super().__new__(mcs, name, bases, namespace, **kwargs)
        class_options = gather_options_for_class(class_object)
        class_object.__options__ = class_options

        offset = 0
        for i, (f_name, field) in enumerate(namespace['__components__'].items()):
            field.index = i
            field.name = f_name
            field.offset = offset
            helpers.merge_dicts(field.__options__, class_options)

            if offset is not None and field.size is not None:
                offset += field.size
            else:
                offset = None

        return class_object


class SerializableContainer(collections.abc.MutableMapping,
                            metaclass=SerializableContainerMeta):
    """A serialization class for container-like objects.

    .. attribute:: __components__

        An :class:`~collections.OrderedDict` of the :class:`Serializable` objects
        comprising the container. *Never* modify or create this yourself.

        :type: :class:`collections.OrderedDict`


    .. attribute:: __options__

        A dictionary of options that all fields will inherit by default.

        :type: dict

        When creating a subclass, you might want to provide some defaults of
        your own. Do *not* declare ``__options__`` at the class level; instead,
        use an internal class named ``Options``::

            class MyStruct(Struct):
                class Options:
                    option_name = 'value'

                ...
    """
    __options__ = None      # type: dict
    __components__ = None   # type: collections.OrderedDict

    def __init__(self, **values):
        extra_keys = values.keys() - self.__components__.keys()
        if extra_keys:
            raise errors.UnexpectedValueError(struct=self, name=extra_keys)

        self.__values__ = values

    def to_stream(self, stream, context=None):
        """Convert the given data into bytes and write it to ``stream``.

        :param io.BytesIO stream:
            The stream to write the serialized data into.
        :param context:
            Additional data to pass to this method. Subclasses must ignore
            anything they don't recognize.
        """
        for name, field in self.__components__.items():
            value = self.__values__.get(name, field.default)
            if value is UNDEFINED:
                raise errors.MissingRequiredValueError(field=field)

            field.dump(stream, value, context)

    def to_bytes(self, context=None):
        """Convert the given data into bytes.

        :param context:
            Additional data to pass to this method. Subclasses must ignore
            anything they don't recognize.

        :return: The serialized data.
        :rtype: bytes
        """
        stream = io.BytesIO()
        self.to_stream(stream, context)
        return stream.getvalue()

    def to_dict(self, fill_missing=False):
        """Convert this struct into a dictionary.

        :param bool fill_missing:
            If ``True``, any unassigned values in this struct will be set to
            their defaults.

        :rtype: collections.OrderedDict
        """
        raise NotImplementedError

    @classmethod
    def from_stream(cls, stream, context=None):
        """Load a struct from the given stream.

        :param io.BytesIO stream:
            The stream to load data from.
        :param context:
            Additional data to pass to the components' :meth:`load` methods.
            Subclasses must ignore anything they don't recognize.

        :return: The loaded struct.
        """
        results = {}

        for name, field in cls.__components__.items():
            results[name] = field.load(stream, context)

        return cls(**results)

    @classmethod
    def from_bytes(cls, data, context=None, exact=True):
        """Load a struct from the given byte string.

        :param bytes data:
            A bytes-like object to get the data from.
        :param context:
            Additional data to pass to this method. Subclasses must ignore
            anything they don't recognize.
        :param bool exact:
            ``data`` must contain exactly the number of bytes required. If not
            all the bytes in ``data`` were used when reading the struct, throw
            an exception.

        :return: The loaded struct.
        """
        stream = io.BytesIO(data)
        loaded_data = cls.from_stream(stream, context)

        if exact and (stream.tell() < len(data) - 1):
            # TODO (dargueta): Better error message.
            raise errors.ExtraneousDataError(
                'Expected to read %d bytes, read %d.'
                % (len(data), stream.tell() + 1))
        return loaded_data

    @classmethod
    def partial_load(cls, stream, last_field=None, context=None):
        """Partially load this object, either until EOF or the named field.

        All fields up to and including the field named in ``last_field`` will be
        loaded from ``stream``.

        If ``last_field`` isn't given, as many complete fields as possible will
        be loaded from ``stream``. Any partially loaded fields will be discarded
        and the stream pointer will be reset to the end of the last complete
        field read.

        :param io.BytesIO stream:
            The stream to load from.
        :param str last_field:
            The name of the last field to load in the object. If given, enough
            bytes for this and all previous fields *must* be present in the
            stream.
        :param context:
            Any object containing extra information to pass to the fields'
            :meth:`load` method.

        :return: The loaded struct.
        """
        if last_field is not None and last_field not in cls.__components__:
            raise ValueError("%s doesn't have a field named %r."
                             % (cls.__name__, last_field))

        result = {}

        for field in cls.__components__.values():
            offset = stream.tell()

            try:
                value = field.load(stream, context)
            except errors.UnexpectedEOFError:
                if last_field is not None:
                    # Hit EOF before we read all the fields we were supposed to.
                    raise

                # Hit EOF in the middle of reading a field. Since the caller
                # didn't specify how far we should read, this isn't an error. Go
                # back to the beginning of this field and return.
                stream.seek(offset)
                return result

            if not field.discard:
                result[field.name] = value

            if field.name == last_field:
                return result

        return cls(**result)

    def partial_dump(self, stream, last_field=None, context=None):
        """Partially dump the object, up to and including the last named field.

        All fields up to and including the field named in ``last_field`` will be
        serialized.

        If ``last_field`` isn't given, as many fields will be serialized as
        possible up to the first missing one.

        :param io.BytesIO stream:
            The stream to dump into.
        :param str last_field:
            The name of the last field in the object to dump.
        :param context:
            Any object containing extra information to pass to the fields'
            :meth:`load` methods.
        """
        data = self.__values__

        for field in self.__components__.values():
            value = data.get(field.name, field.default)
            if value is UNDEFINED:
                # Field is missing from the dump data. If the caller wants us to
                # dump only the fields that're defined, we can bail out now.
                if last_field is None:
                    return
                elif field.required:
                    # Caller wants us to dump up to and including ``last_field``
                    # so we need to crash.
                    raise errors.MissingRequiredValueError(field=field)

            field.dump(stream, value, context)

            if field.name == last_field:
                return

    # Container methods
    def __getitem__(self, item):
        return self.__values__[item]

    def __setitem__(self, field_name, value):
        if field_name not in self.__components__:
            raise KeyError('%r has field named %r.'
                           % (type(self).__name__, field_name))
        self.__values__[field_name] = value

    def __delitem__(self, field_name):
        if field_name not in self.__components__:
            raise KeyError('Struct %r has such field named %r.'
                           % (type(self).__name__, field_name))
        del self.__values__[field_name]

    def __iter__(self):
        raise NotImplementedError

    def __len__(self):
        return len(bytes(self))

    def __bytes__(self):
        return self.to_bytes()
