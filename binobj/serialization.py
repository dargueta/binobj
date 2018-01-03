"""Stuff for serializing data."""

import abc
import collections
import copy
import io

from binobj import errors
from binobj import helpers


# Normally a plain :class:`object` instance would be used as a sentinel value,
# but `copy.deepcopy` uses pickling which creates a new instance of the object.
# That breaks the assumption that only one instance of this will ever exist at a
# time, hence the following abomination.


def UNDEFINED():  # pylint: disable=invalid-name
    """A sentinel value used to indicate that a setting or field is undefined.

    .. note::

        This sentinel value is implemented as a function for stupid reasons and
        may change at any time. Never call it or even assume it's callable.
    """
    raise RuntimeError('Only use this sentinel as a value and never call it.')


def DEFAULT():  # pylint: disable=invalid-name
    """A sentinel value used to indicate that the default value of a setting
    should be used. We need this because sometimes ``None`` is a valid value for
    that setting.

    .. note::

        This sentinel value is implemented as a function for stupid reasons and
        may change at any time. Never call it or even assume it's callable.
    """
    raise RuntimeError('Only use this sentinel as a value and never call it.')


#: A read-only dictionary of predefined options for serializable objects.
_DEFAULT_OPTIONS = {
    'allow_null': True,
    'const': UNDEFINED,
    'default': UNDEFINED,
    'null_value': DEFAULT,
}


# TODO (dargueta) Cache the return value for this without borking singletons.
#
# The problem with caching the return value is that a deep copy needs to be made
# in Serializable.__init__. This is normally fine, except that `copy.deepcopy`
# uses pickling to perform a deep copy, so there end up being multiple copies of
# the ``UNDEFINED``, ``DEFAULT``, and ``HALT`` sentinel objects. Identity checks
# (the exact reason we have sentinels) will no longer work. :(
def gather_options_for_class(klass):
    """Build a dictionary of a :class:`Serializable` object's settings, including
    values defined in parent classes.

    :param type klass:
        A :class:`Serializable` class object (not an instance) that we want to
        get the options for.

    :return: A dictionary of the class' defined options.
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
    if not issubclass(klass, Serializable):
        return options

    # Determine all the options defined in the parent classes
    for parent_class in reversed(klass.__mro__):
        if parent_class not in seen:
            _r_gather_options_for_class(parent_class, options, seen)
        seen.add(parent_class)

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

    .. attribute:: size

        The size of this object, in bytes.
    """
    class Options:
        """An object used for defining settings on a per-class basis."""

    def __init__(self, *, size=None, **kwargs):
        self.size = size
        self.__options__ = gather_options_for_class(type(self))
        self.__options__.update(kwargs)
        super().__init__()

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

        if exact and (stream.tell() < len(data) - 1):
            # TODO (dargueta): Better error message.
            raise errors.ExtraneousDataError(
                'Expected to read %d bytes, read %d.'
                % (len(data), stream.tell() + 1))
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


class SerializableContainer(Serializable, metaclass=SerializableContainerMeta):
    """A serialization class for container-like objects.

    .. attribute:: __components__

        An :class:`~collections.OrderedDict` of the :class:`Serializable` objects
        comprising the container. *Never* modify this yourself.
    """
    __components__ = None   # type: collections.OrderedDict

    def _do_dump(self, stream, data, context):
        """Convert the given data into bytes and write it to ``stream``.

        :param io.BytesIO stream:
            A stream to write the serialized data into.
        :param dict data:
            The data to dump.
        :param context:
            Additional data to pass to the :meth:`dump` function.
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
                const = component.__options__['const']
                default = component.__options__['default']
                if const is not UNDEFINED:
                    value = const
                elif default is not UNDEFINED:
                    value = default
                else:
                    raise errors.MissingRequiredValueError(field=component)

            component.dump(stream, value, context)

    def _do_load(self, stream, context=None):
        """Load a structure from the given byte stream.

        :param io.BytesIO stream:
            A bytes stream to read data from.
        :param context:
            Additional data to pass to the deserialization function. Subclasses
            must ignore anything they don't recognize.

        :return: The deserialized data.
        :rtype: collections.OrderedDict
        """
        result = collections.OrderedDict()
        for name, component in self.__components__.items():
            value = component.load(stream, context)
            if not component.discard:
                result[name] = value

        return result

    def partial_load(self, stream, last_field=None, context=None):
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

        :return: The deserialized data.
        :rtype: collections.OrderedDict
        """
        if last_field is not None and last_field not in self.__components__:
            raise ValueError(
                "%s doesn't have a field named %r." % (self, last_field))

        result = collections.OrderedDict()
        for field in self.__components__.values():
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

        return result

    def partial_dump(self, stream, data, last_field=None, context=None):
        """Partially dump the object, up to and including the last named field.

        All fields up to and including the field named in ``last_field`` will be
        serialized.

        If ``last_field`` isn't given, as many fields will be serialized as
        possible up to the first missing one.

        :param io.BytesIO stream:
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
            field.dump(stream, value, context)

            if field.name == last_field:
                return
