"""Classes defining structures and unions."""

import abc
import collections
import collections.abc
import io
import types

from binobj import errors
from binobj import fields


__all__ = ['Struct']


class StructMeta(abc.ABCMeta):
    """The metaclass for all serializable objects composed of other serializable
    objects.

    It defines the ``__components__`` class variable and sets some values on the
    :class:`Field` components such as the name and index.
    """
    @classmethod
    def __prepare__(mcs, name, bases):      # pylint: disable=unused-argument
        return collections.OrderedDict()

    def __new__(mcs, name, bases, namespace, **kwargs):
        components = collections.OrderedDict(
            (name, item)
            for name, item in namespace.items()
            if isinstance(item, fields.Field)
        )

        namespace['__components__'] = components

        class_object = super().__new__(mcs, name, bases, namespace, **kwargs)

        offset = 0
        for i, (f_name, field) in enumerate(components.items()):
            field.bind_to_container(f_name, i, offset)

            if offset is not None and field.size is not None:
                offset += field.size
            else:
                offset = None

        return class_object


def recursive_to_dicts(item, fill_missing=False):
    """When a :class:`Struct` is converted to a dictionary, ensure that any
    nested structures are also converted to dictionaries.
    """
    if isinstance(item, Struct):
        return item.to_dict(fill_missing=fill_missing)
    elif isinstance(item, collections.abc.Mapping):
        return collections.OrderedDict(
            (recursive_to_dicts(k, fill_missing), recursive_to_dicts(v, fill_missing))
            for k, v in item.items()
        )
    elif isinstance(item, collections.abc.Sequence) \
            and not isinstance(item, (str, bytes)):
        return [recursive_to_dicts(v, fill_missing) for v in item]
    return item


class Struct(collections.abc.MutableMapping, metaclass=StructMeta):
    """An ordered collection of fields and other structures."""
    __components__ = types.MappingProxyType({})  # type: collections.OrderedDict

    def __init__(self, **values):
        extra_keys = set(values.keys() - self.__components__.keys())
        if extra_keys:
            raise errors.UnexpectedValueError(struct=self, name=extra_keys)

        self.__values__ = values

    def to_stream(self, stream, context=None, all_fields=None):
        """Convert the given data into bytes and write it to ``stream``.

        :param io.BufferedIOBase stream:
            The stream to write the serialized data into.
        :param context:
            Additional data to pass to this method. Subclasses must ignore
            anything they don't recognize.
        """
        my_fields = dict(self)

        for name, field in self.__components__.items():
            value = self.__values__.get(name, field.default)
            if value is fields.UNDEFINED:
                raise errors.MissingRequiredValueError(field=field)

            field.dump(stream, value, context=context, all_fields=my_fields)

    def to_bytes(self, context=None):
        """Convert the given data into bytes.

        :param context:
            Additional data to pass to this method. Subclasses must ignore
            anything they don't recognize.

        :return: The serialized data.
        :rtype: bytes
        """
        my_fields = dict(self)

        stream = io.BytesIO()
        self.to_stream(stream, context=context, all_fields=my_fields)
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

        return recursive_to_dicts(dct, fill_missing)

    @classmethod
    def from_stream(cls, stream, context=None, loaded_fields=None):
        """Load a struct from the given stream.

        :param io.BufferedIOBase stream:
            The stream to load data from.
        :param context:
            Additional data to pass to the components' :meth:`load` methods.
            Subclasses must ignore anything they don't recognize.

        :return: The loaded struct.
        """
        results = {}

        for name, field in cls.__components__.items():
            results[name] = field.load(stream, context=context,
                                       loaded_fields=results)

        return cls(**results)

    @classmethod
    def from_bytes(cls, data, context=None, exact=True, loaded_fields=None):
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
        loaded_data = cls.from_stream(stream, context=context,
                                      loaded_fields=loaded_fields)

        if exact and (stream.tell() < len(data) - 1):
            raise errors.ExtraneousDataError(
                'Read %d bytes, but there are %d in the input data.'
                % (stream.tell() + 1, len(data)),
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

        :param io.BufferedIOBase stream:
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
                value = field.load(stream, context=context, loaded_fields=result)
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

    @classmethod
    def get_field(cls, stream, name, context=None):
        """Return the value of a single field.

        .. note ::
            If the field isn't at a fixed offset from the beginning of the
            struct (e.g. a variable-length field occurs before it) then the
            entire struct up to and including this field must be read.
            Unfortunately, this means that unrelated validation errors can be
            thrown if other fields are invalid.

        :param io.BufferedIOBase stream:
            The stream to read from. It's assumed that the stream pointer is
            positioned at the start of a struct. The stream pointer is returned
            to its original position even if an exception occurred.
        :param str name:
            The name of the field to retrieve.
        :param context:
            Optional. Any object containing extra information to pass to the
            :meth:`load` method of the field. For fields located at a variable
            offset, this will be passed to the :meth:`load` method of *each*
            field read.

        :return: The value of the field in the struct data.

        :raise UnexpectedEOFError:
            The end of the stream was reached before the requested field could
            be completely read.
        """
        if name not in cls.__components__:
            raise ValueError("%s doesn't have a field named %r."
                             % (cls.__name__, name))

        field = cls.__components__[name]
        original_offset = stream.tell()

        # If the field is at a fixed offset from the beginning of the struct,
        # then we can read and return it directly.
        if field.offset is not None:
            try:
                stream.seek(original_offset + field.offset)
                return field.load(stream, context=context, loaded_fields={})
            finally:
                stream.seek(original_offset)

        # If we get here then the field is *not* at a fixed offset from the
        # beginning of the struct and we have to read everything up to it. This
        # can unfortunately result in validation errors if there is data before
        # the desired field that's invalid.
        try:
            loaded_data = cls.partial_load(stream, name, context)
        finally:
            stream.seek(original_offset)
        return loaded_data[name]

    def partial_dump(self, stream, last_field=None, context=None):
        """Partially dump the object, up to and including the last named field.

        All fields up to and including the field named in ``last_field`` will be
        serialized.

        If ``last_field`` isn't given, as many fields will be serialized as
        possible up to the first missing one.

        :param io.BufferedIOBase stream:
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
            if value is fields.UNDEFINED:
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
            if value is not fields.UNDEFINED:
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
                if field_value is fields.UNDEFINED:
                    raise errors.VariableSizedFieldError(field=field)
                size += len(field.dumps(field_value))

        return size

    def __eq__(self, other):
        if isinstance(other, Struct):
            other = other.to_dict(fill_missing=True)
        return self.to_dict(fill_missing=True) == other

    def __bytes__(self):
        return self.to_bytes()


# TODO (dargueta): Implement unions and bitfields.
