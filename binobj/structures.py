"""Classes defining structures and unions."""

import abc
import collections
import collections.abc
import io
import types
import warnings

from binobj import errors
from binobj import fields
from binobj import validation


__all__ = ['Struct']


class StructMeta(abc.ABCMeta):
    """The metaclass for all serializable objects composed of other serializable
    objects.

    It defines the ``__components__`` and ``__validators__`` class variables
    and sets some values on the :class:`~binobj.fields.Field` components such as
    the name and index.
    """
    @classmethod
    def __prepare__(mcs, name, bases):      # pylint: disable=unused-argument
        return collections.OrderedDict()

    def __new__(mcs, class_name, bases, namespace, **kwargs):
        # Build a list of all of the base classes that appear to be Structs. If
        # anything else uses StructMeta as a metaclass then we're in trouble.
        struct_bases = [b for b in bases if issubclass(type(b), mcs)]

        if len(struct_bases) > 1:
            raise errors.MultipleInheritanceError(struct=class_name)

        components = collections.OrderedDict()

        if struct_bases:
            # Build a dictionary of all of the fields in the parent struct first,
            # then add in the fields defined in this struct.
            base = struct_bases[0]

            for comp_name, item in base.__components__.items():
                if isinstance(item, fields.Field):
                    components[comp_name] = item

            validators = {
                # Copy the dict of field validators for the parent struct,
                # making a separate copy of the validator list for this class.
                # This is so that child classes can add validators for fields
                # defined in the parent class without affecting the parent class.
                'fields': {
                    f_name: list(v_list)
                    for f_name, v_list in base.__validators__['fields'].items()
                },

                # Similarly, make a copy of the struct validators of the parent
                # class.
                'struct': list(base.__validators__['struct']),
            }

            # Start the byte offset at the end of the base class. We won't be able
            # to do this if the base class has variable-length fields.
            offset = base.get_size()
        else:
            # Else: This struct doesn't inherit from another struct, so we're
            # starting at offset 0. There are no field or struct validators to
            # copy.
            offset = 0
            validators = {
                'fields': {},
                'struct': [],
            }

        field_index = len(components)

        # Bind all of this struct's fields to this struct. It's HIGHLY important
        # that we don't accidentally bind the superclass' fields to this struct.
        # That's why we're iterating over ``namespace`` and *then* adding the
        # field into the ``components`` dict.
        for item_name, item in namespace.items():
            if not isinstance(item, fields.Field):
                continue
            elif item_name in components:
                raise errors.FieldRedefinedError(struct=class_name, field=item)

            item.bind_to_container(item_name, field_index, offset)
            if offset is not None and item.size is not None:
                offset += item.size
            else:
                offset = None

            components[item_name] = item
            validators['fields'][item_name] = []

            field_index += 1

        # Iterate through all fields on the child class and set the validators.

        for item in namespace.values():
            if not isinstance(item, validation.ValidatorMethodWrapper):
                continue

            if item.field_names:
                # Attach this validator to each named field.
                for field_name in item.field_names:
                    validators['fields'][field_name].append(item)
            else:
                # Validator doesn't define any fields, must be a validator for
                # the entire struct.
                validators['struct'].append(item)

        namespace['__components__'] = components
        namespace['__validators__'] = validators
        return super().__new__(mcs, class_name, bases, namespace, **kwargs)


def recursive_to_dicts(item, fill_missing=False):
    """When a :class:`Struct` is converted to a dictionary, ensure that any
    nested structures are also converted to dictionaries.

    :param item:
        Anything. If it's an unsupported type it'll get returned as-is.
    :param bool fill_missing:
        The ``fill_missing`` argument value to pass to a struct's ``to_dict()``
        method.
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
    """An ordered collection of fields and other structures.

    .. attribute:: __components__

        An ordered mapping of the field names to their :class:`~binobj.fields.Field`
        object definitions.

        :type: :class:`collections.OrderedDict`
    """
    __components__ = types.MappingProxyType({})     # type: collections.OrderedDict
    __validators__ = types.MappingProxyType({       # type: dict
        'fields': types.MappingProxyType({}),
        'struct': (),
    })

    def __init__(self, **values):
        extra_keys = set(values.keys() - self.__components__.keys())
        if extra_keys:
            raise errors.UnexpectedValueError(struct=self, name=extra_keys)

        self.__values__ = values

    def validate_contents(self):
        """Validate the stored values in this struct.

        :raise ~binobj.errors.ValidationError: Validation failed.

        .. versionadded:: 0.4.0
        """
        full_struct = self.to_dict()

        for f_name, validators in self.__validators__['fields'].items():
            f_obj = self.__components__[f_name]

            # Remove once to_dump(fill_missing=True) is gone
            if f_name not in full_struct:
                raise errors.MissingRequiredValueError(field=f_obj)

            value = full_struct[f_name]

            # First, invoke the validators defined on the field object.
            for validator in f_obj.validators:
                validator(value)

            # Second, invoke the validator methods for the field defined on this
            # Struct.
            for validator in validators:
                validator(self, f_obj, value)

        # Validate the entirety of the struct.
        for validator in self.__validators__['struct']:
            validator(self, full_struct)

    def to_stream(self, stream, context=None):
        """Convert the given data into bytes and write it to ``stream``.

        :param io.BufferedIOBase stream:
            The stream to write the serialized data into.
        :param context:
            Additional data to pass to this method. Subclasses must ignore
            anything they don't recognize.
        """
        self.validate_contents()
        all_fields = self.to_dict(True)

        for field_name, value in all_fields.items():
            # Remove once to_dump(fill_missing=True) is gone
            if value is fields.UNDEFINED:
                raise errors.MissingRequiredValueError(field=field_name)

            field_obj = self.__components__[field_name]
            field_obj.dump(stream, value, context=context, all_fields=all_fields)

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

        The primary use for this method is converting a loaded :class:`Struct`
        into native Python types. As such, validation is *not* performed since
        that was done while loading.

        :param bool fill_missing:
            Controls what to do about required values that haven't been set on
            the struct yet.

            If ``False`` (the default), unassigned values in this struct are
            omitted from the returned dictionary. If ``True``, they're included
            but set to :data:`~binobj.fields.UNDEFINED`.

        :rtype: collections.OrderedDict

        .. deprecated:: 0.4.0

            Support for ignoring missing required values will be removed in a
            future version, as this method is mostly supposed to be used after
            loading. Calling ``to_dict()`` with an unassigned required value
            will trigger a :class:`~binobj.errors.MissingRequiredValueError`
            exception.

        .. versionchanged:: 0.3.0

            This now recursively calls :meth:`to_dict` on all nested structs and
            arrays so that the returned dictionary is completely converted, not
            just the first level.
        """
        if fill_missing:
            warnings.warn(
                'Support for ignoring missing values will be removed from '
                'to_dict() in a future release.', DeprecationWarning)

        dct = collections.OrderedDict()
        for field in self.__components__.values():
            try:
                dct[field.name] = field.compute_value_for_dump(self)
            except errors.MissingRequiredValueError:
                if fill_missing:
                    dct[field.name] = fields.UNDEFINED

        return recursive_to_dicts(dct, fill_missing)

    @classmethod
    def from_stream(cls, stream, context=None):
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

        instance = cls(**results)
        instance.validate_contents()
        return instance

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

        .. note::

            Because the struct is only partially loaded, validators are *not*
            executed.

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

    @classmethod
    def get_size(cls):
        """Return the size of this struct in bytes, or ``None`` if there are
        variable-sized fields that can't be resolved.

        Do *not* use this on instances; use ``len(instance)`` instead.

        :return: The struct's size, in bytes.
        :rtype: int

        .. versionadded:: 0.3.0
        """
        sizes = [f.size for f in cls.__components__.values()]

        # Don't try summing the sizes of the fields if anything in there isn't
        # an integer.
        if all(isinstance(s, int) for s in sizes):
            return sum(sizes)
        return None

    # Container methods

    # DO NOT remove this. It prevents the infinite recursion that the default
    # implementation in MutableMapping would trigger.
    def __contains__(self, item):
        return item in self.__values__

    def __getitem__(self, field_name):
        if field_name not in self.__components__:
            raise KeyError('Struct %r has no field named %r.'
                           % (type(self).__name__, field_name))
        return getattr(self, field_name)

    def __setitem__(self, field_name, value):
        if field_name not in self.__components__:
            raise KeyError('Struct %r has no field named %r.'
                           % (type(self).__name__, field_name))
        setattr(self, field_name, value)

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
        size = 0
        for field in self.__components__.values():
            if field.size is not None:
                size += field.size
            else:
                field_value = field.compute_value_for_dump(self)
                size += len(field.dumps(field_value))

        return size

    def __eq__(self, other):
        if isinstance(other, Struct):
            other = other.to_dict(fill_missing=True)
        return self.to_dict(fill_missing=True) == other

    def __bytes__(self):
        return self.to_bytes()
