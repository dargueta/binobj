"""Base classes for representing objects that can be loaded and stored as binary
data."""

import abc
import collections
import collections.abc
import copy
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


class OptionProperty:
    """An attribute on an object that's stored in its ``__options__`` dict.

    :param default:
        The default value for this option. If not given, the option is considered
        a required keyword argument to the constructor.

    .. attribute:: name

        The name of this field. Its value is set by the containing object's
        metaclass, so there's no constructor argument for it. Defaults to
        ``None``.

        :type: str
    """
    def __init__(self, *, name=None, **kwargs):
        self.required = 'default' not in kwargs
        self.default = kwargs.pop('default', UNDEFINED)
        self.name = name

        if kwargs:
            raise TypeError('Unrecognized keyword argument(s): '
                            + ', '.join(repr(k) for k in kwargs))

    def __get__(self, instance, owner):
        if instance is None:
            return self
        elif self.required and self.name not in instance.__options__:
            raise ValueError('No value set for option: %r' % self.name)
        return instance.__options__.setdefault(self.name, self.default)

    def __set__(self, instance, value):
        instance.__options__[self.name] = value
        return value

    def __repr__(self):
        return '%s(%r, required=%r, default=%r)' % (
            type(self).__name__, self.name, self.required, self.default)


def gather_options_for_class(klass):
    """Build a dictionary of an object's settings, including values defined in
    parent classes.

    :param type klass:
        A class object (not an instance) that we want to get the options for.
        The class must have an internal class named ``Options``.

    :return: A dictionary of the class' defined options, plus a few defaults.
    :rtype: dict
    """
    return _r_gather_options_for_class(klass, {}, set())


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


class FieldMeta(type):
    """The metaclass for all fields.

    All it does is set the options' names on their instances.
    """
    def __new__(mcs, name, bases, namespace, **kwargs):
        class_object = super().__new__(mcs, name, bases, namespace, **kwargs)

        for name, obj in namespace.items():
            if isinstance(obj, OptionProperty):
                obj.name = name

        return class_object


class SerializableContainerMeta(abc.ABCMeta):
    """The metaclass for all serializable objects composed of other serializable
    objects.

    It defines the ``__components__`` class variable and sets some values on the
    :class:`Field` components such as the name and index.
    """
    @classmethod
    def __prepare__(mcs, name, bases):      # pylint: disable=unused-argument
        return collections.OrderedDict()

    def __new__(mcs, name, bases, namespace, **kwargs):
        # TODO (dargueta): Need to get fields from the superclasses as well.
        namespace['__components__'] = collections.OrderedDict(
            (name, comp)
            for name, comp in namespace.items()
            if issubclass(type(type(comp)), FieldMeta)
            # TODO (dargueta): This is a hacky way to detect a Field.
            # Weird roundabout way of seeing if this is a field -- checks to see
            # if the metaclass of the object is FieldMeta.
        )

        class_object = super().__new__(mcs, name, bases, namespace, **kwargs)
        class_options = gather_options_for_class(class_object)
        class_object.__options__ = class_options

        offset = 0
        for i, (f_name, field) in enumerate(namespace['__components__'].items()):
            field.index = i
            field.name = f_name
            field.offset = offset
            field.__options__ = collections.ChainMap(field.__options__,
                                                     class_object.__options__)

            if offset is not None and field.size is not None:
                offset += field.size
            else:
                offset = None

        return class_object


class SerializableContainer(collections.abc.MutableMapping,
                            metaclass=SerializableContainerMeta):
    """A serialization class for container-like objects.

    .. attribute:: __components__

        An :class:`~collections.OrderedDict` of the :class:`Field` objects
        comprising the container. *Never* modify or create this yourself.

        :type: :class:`collections.OrderedDict`

    .. attribute:: __options__

        A dictionary of options that all fields will inherit by default.

        :type: dict
    """
    __options__ = None      # type: dict
    __components__ = None   # type: collections.OrderedDict

    def __init__(self, **values):
        extra_keys = set(values.keys() - self.__components__.keys())
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
            their defaults or :data:`UNDEFINED` if they have no defined default.

        :rtype: collections.OrderedDict
        """
        dct = collections.OrderedDict()
        for field in self.__components__.values():
            if field.name in self.__values__:
                dct[field.name] = self.__values__[field.name]
            elif fill_missing:
                dct[field.name] = field.default

        return dct

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
                'Expected %d bytes, got %d.' % (len(data), stream.tell() + 1),
                offset=stream.tell())
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
                break

            if not field.discard:
                result[field.name] = value

            if field.name == last_field:
                break

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
            raise KeyError('Struct %r has no field named %r.'
                           % (type(self).__name__, field_name))
        self.__values__[field_name] = value

    def __delitem__(self, field_name):
        if field_name not in self.__components__:
            raise KeyError('Struct %r has no field named %r.'
                           % (type(self).__name__, field_name))
        self.__values__.pop(field_name, None)

    def __iter__(self):
        for name, value in self.__values__.items():
            if value is not UNDEFINED:
                yield name

    def __len__(self):
        sizes = [f.size for f in self.__components__.values()]
        if None not in sizes:
            return sum(sizes)

        # If we get here then there's at least one variable-length field in this
        # struct. To find the total size, we have to add up the sizes of the
        # fixed-length fields and then try serializing all of the variable-length
        # fields.
        size = 0
        for name, field in self.__components__.items():
            if field.size is not None:
                size += field.size
            else:
                field_value = self.__values__.get(name, field.default)
                if field_value is UNDEFINED:
                    raise errors.VariableSizedFieldError(field=field)
                size += len(field.dumps(field_value))

        return size

    def __bytes__(self):
        return self.to_bytes()
