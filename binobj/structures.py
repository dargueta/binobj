"""Classes defining structures and unions."""

import abc
import collections
import collections.abc
import io
import types

from binobj import errors
from binobj import fields
from binobj import validation


__all__ = ['Struct']


class StructMeta(abc.ABCMeta):
    """The metaclass for all serializable objects composed of other serializable
    objects.

    It defines the ``__components__`` and ``__validators__`` class variables
    and sets some values on the :class:`~binobj.fields.base.Field` components
    such as the name and index.
    """
    @classmethod
    def __prepare__(cls, name, bases):      # pylint: disable=unused-argument
        return collections.OrderedDict()

    def __new__(cls, class_name, bases, namespace, **kwargs):
        # Build a list of all of the base classes that appear to be Structs. If
        # anything else uses StructMeta as a metaclass then we're in trouble,
        # since this will detect that as a second base class.
        struct_bases = [b for b in bases if issubclass(type(b), cls)]

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

        validators['fields'].update({
            name: []
            for name, obj in namespace.items()
            if isinstance(obj, fields.Field)
        })

        field_index = len(components)

        cls._bind_fields(class_name, namespace, components, field_index, offset)
        cls._bind_validators(namespace, validators)

        namespace['__components__'] = components
        namespace['__validators__'] = validators
        return super().__new__(cls, class_name, bases, namespace, **kwargs)

    @staticmethod
    def _bind_fields(class_name, namespace, components, field_index, offset):
        """Bind all of this struct's fields to this struct."""
        # It's HIGHLY important that we don't accidentally bind the superclass'
        # fields to this struct. That's why we're iterating over ``namespace``
        # and adding the field into the ``components`` dict *inside* the loop.
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

            field_index += 1

    @staticmethod
    def _bind_validators(namespace, validators):
        """Find all defined validators and assign them to their fields."""
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


def recursive_to_dicts(item):
    """When a :class:`Struct` is converted to a dictionary, ensure that any
    nested structures are also converted to dictionaries.

    :param item:
        Anything. If it's an unsupported type it'll get returned as is.
    """
    if isinstance(item, Struct):
        return item.to_dict()
    if isinstance(item, collections.abc.Mapping):
        return collections.OrderedDict(
            (recursive_to_dicts(k), recursive_to_dicts(v))
            for k, v in item.items()
        )
    if isinstance(item, collections.abc.Sequence) \
            and not isinstance(item, (str, bytes, bytearray)):
        return [recursive_to_dicts(v) for v in item]
    return item


class Struct(metaclass=StructMeta):
    """An ordered collection of fields and other structures.

    .. attribute:: __components__

        An ordered mapping of the field names to their :class:`~binobj.fields.base.Field`
        object definitions.

        :type: :class:`collections.OrderedDict`

    .. versionchanged:: 0.5.0
        A Struct will compare equal to :data:`~binobj.fields.base.UNDEFINED` if
        and only if all of its fields are also undefined.

    .. deprecated:: 0.5.0
        Comparison to anything other than another Struct or mapping is deprecated.
        In the future, it will trigger a :class:`TypeError`.
    """
    __components__ = types.MappingProxyType({})     # type: collections.OrderedDict
    __validators__ = types.MappingProxyType({
        'fields': types.MappingProxyType({}),
        'struct': (),
    })                                              # type: dict

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
        # WARNING: Converting to a dictionary first is required to avoid infinite
        # recursion problems. We can't use `self`.
        full_struct = self.to_dict()

        for f_name, validators in self.__validators__['fields'].items():
            f_obj = self.__components__[f_name]

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

        # We can't pass `self` to all_fields because Structs can't be used with
        # dictionary expansion (e.g. **kwargs). It'd be a nasty surprise for
        # fields expecting a dictionary.
        all_fields = self.to_dict()

        for field in self.__components__.values():
            value = field.compute_value_for_dump(all_fields)
            if value is not fields.NOT_PRESENT:
                field.dump(stream, value, context=context, all_fields=all_fields)

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

    def to_dict(self):
        """Convert this struct into a dictionary.

        The primary use for this method is converting a loaded :class:`Struct`
        into native Python types. As such, validation is *not* performed since
        that was done while loading.

        :rtype: collections.OrderedDict

        :raise ~binobj.errors.MissingRequiredValueError:
            One or more fields don't have assigned values.

        .. versionchanged:: 0.3.0
            This now recursively calls :meth:`.to_dict` on all nested structs and
            arrays so that the returned dictionary is completely converted, not
            just the first level.
        """
        dct = collections.OrderedDict(
            (field.name, field.compute_value_for_dump(self))
            for field in self.__components__.values()
        )
        return recursive_to_dicts(dct)

    @classmethod
    def from_stream(cls, stream, context=None):
        """Load a struct from the given stream.

        :param io.BufferedIOBase stream:
            The stream to load data from.
        :param context:
            Additional data to pass to the components'
            :meth:`~binobj.fields.base.Field.load` methods. Subclasses must
            ignore anything they don't recognize.

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
            :meth:`~binobj.fields.base.Field.load` method.

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
            :meth:`~binobj.fields.base.Field.load` method of the field. For fields
            located at a variable offset, this will be passed to the
            :meth:`~binobj.fields.base.Field.load` method of *each* field read.

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
            :meth:`~binobj.fields.base.Field.load` methods.
        """
        data = self.__values__

        for field in self.__components__.values():
            value = data.get(field.name, field.default)
            if value is fields.UNDEFINED:
                # Field is missing from the dump data. If the caller wants us to
                # dump only the fields that're defined, we can bail out now.
                if last_field is None:
                    return
                if field.required:
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
        # Allow comparison to UNDEFINED. The result is True if all fields in this
        # struct are undefined, False otherwise.
        if other is fields.UNDEFINED:
            return all(v is fields.UNDEFINED for v in self.__values__.values())

        # Compare only defined values by using __iter__ to get the keys that are
        # defined.
        self_values = recursive_to_dicts({n: self[n] for n in list(self)})

        if not isinstance(other, (Struct, collections.abc.Mapping)):
            return False

        other_values = recursive_to_dicts({n: other[n] for n in list(other)})
        return other_values == self_values

    def __bytes__(self):
        return self.to_bytes()
