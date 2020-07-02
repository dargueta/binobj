"""Classes defining structures and unions."""

import abc
import collections
import collections.abc
import copy
import io
import typing
from typing import Any
from typing import BinaryIO
from typing import Dict
from typing import Iterator
from typing import List
from typing import Mapping
from typing import MutableMapping
from typing import Optional
from typing import overload
from typing import Sequence
from typing import Tuple
from typing import Type
from typing import TypeVar

import attr

from binobj import decorators
from binobj import errors
from binobj import fields
from binobj.typedefs import MethodFieldValidator
from binobj.typedefs import MutableStrDict
from binobj.typedefs import StrDict
from binobj.typedefs import StructValidator


__all__ = ["Struct"]


T = TypeVar("T")
K = TypeVar("K")
V = TypeVar("V")
TStruct = TypeVar("TStruct", covariant=True, bound="Struct")


@attr.s
class StructMetadata:
    """Info about the :class:`.Struct` it belongs to, like its fields and validators.

    This class should be considered part of how Structs are implemented. It's only of
    use to people writing wrapper classes or otherwise enhancing the behavior of the
    default :class:`.Struct` class.
    """

    components = attr.ib(
        type=Dict[str, fields.Field[Any]], factory=collections.OrderedDict
    )
    struct_validators = attr.ib(type=List[StructValidator], factory=list)
    field_validators = attr.ib(type=Dict[str, List[MethodFieldValidator]], factory=dict)
    defaults = attr.ib(type=Dict[str, Any], factory=dict)


class StructMeta(abc.ABCMeta):
    """The metaclass for all serializable objects composed of other serializable
    objects.

    It defines the ``__binobj_struct__`` class variables and sets some values on the
    :class:`~binobj.fields.base.Field` components such as its name and index.
    """

    # MyPy is kinda forcing me to use dunderscore names for arguments just because
    # typeshed does it this way. The stupidity... >:[
    @classmethod
    def __prepare__(
        mcs, __name: str, __bases: Tuple[type, ...], **_kwargs: Any
    ) -> MutableStrDict:
        return collections.OrderedDict()

    def __new__(
        mcs: Type["StructMeta"],
        class_name: str,
        bases: Tuple[type, ...],
        namespace: Dict[str, Any],
    ) -> "StructMeta":
        # Build a list of all of the base classes that appear to be Structs. If anything
        # else uses StructMeta as a metaclass then we're in trouble, since this will
        # detect that as a second base class.
        struct_bases = [b for b in bases if issubclass(type(b), mcs)]

        if len(struct_bases) > 1:
            raise errors.MultipleInheritanceError(struct=class_name)

        metadata = StructMetadata()

        if struct_bases:
            # Build a dictionary of all of the fields in the parent struct first,
            # then add in the fields defined in this struct.
            base = typing.cast(Type["Struct"], struct_bases[0])

            for comp_name, item in base.__binobj_struct__.components.items():
                if isinstance(item, fields.Field):
                    metadata.components[comp_name] = item

            # Copy the dict of field validators for the parent struct, making a separate
            # copy of the validator list for this class. This is so that child classes
            # can add validators for fields defined in the parent class without
            # affecting the parent class.
            metadata.field_validators = {
                f_name: list(v_list)
                for f_name, v_list in base.__binobj_struct__.field_validators.items()
            }

            # Similarly, make a copy of the struct validators of the parent class.
            metadata.struct_validators = list(base.__binobj_struct__.struct_validators)

            # Start the byte offset at the end of the base class. We won't be able to do
            # this if the base class has variable-length fields.
            offset = base.get_size()
        else:
            # Else: This struct doesn't inherit from another struct, so we're starting
            # at offset 0. There are no field or struct validators to copy.
            offset = 0

        metadata.field_validators.update(
            {
                name: []
                for name, obj in namespace.items()
                if isinstance(obj, fields.Field)
            }
        )

        field_index = len(metadata.components)

        mcs._bind_fields(
            class_name, namespace, metadata.components, field_index, offset
        )
        mcs._bind_validators(namespace, metadata)

        namespace["__binobj_struct__"] = metadata
        # TODO (dargueta): Figure out how metaclasses are supposed to work with MyPy
        return super().__new__(mcs, class_name, bases, namespace)  # type: ignore

    @staticmethod
    def _bind_fields(
        class_name: str,
        namespace: StrDict,
        components: MutableMapping[str, fields.Field[Any]],
        field_index: int,
        offset: Optional[int],
    ) -> None:
        """Bind all of this struct's fields to this struct."""
        # It's HIGHLY important that we don't accidentally bind the superclass'
        # fields to this struct. That's why we're iterating over ``namespace``
        # and adding the field into the ``components`` dict *inside* the loop.
        for item_name, item in namespace.items():
            if not isinstance(item, fields.Field):
                continue
            if item_name in components:
                raise errors.FieldRedefinedError(struct=class_name, field=item)

            item.bind_to_container(item_name, field_index, offset)
            if offset is not None and item.size is not None:
                offset += item.size
            else:
                offset = None

            components[item_name] = item

            field_index += 1

    @staticmethod
    def _bind_validators(namespace: StrDict, validators) -> None:
        """Find all defined validators and assign them to their fields."""
        for item in namespace.values():
            if not isinstance(item, decorators.ValidatorMethodWrapper):
                continue

            if item.field_names:
                # Attach this validator to each named field.
                for field_name in item.field_names:
                    validators.field_validators[field_name].append(item)
            else:
                # Validator doesn't define any fields, must be a validator for
                # the entire struct.
                validators.struct_validators.append(item)


@overload
def recursive_to_dicts(item: "Struct") -> MutableMapping[str, Any]:
    ...


@overload
def recursive_to_dicts(item: Mapping[K, V]) -> MutableMapping[K, V]:
    ...


@overload
def recursive_to_dicts(item: Sequence[T]) -> List[T]:
    ...


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
            (recursive_to_dicts(k), recursive_to_dicts(v)) for k, v in item.items()
        )
    if isinstance(item, collections.abc.Sequence) and not isinstance(
        item, (str, bytes, bytearray)
    ):
        return [recursive_to_dicts(v) for v in item]
    return item


class Struct(metaclass=StructMeta):
    """An ordered collection of fields and other structures.

    .. attribute:: __binobj_struct__

        A class attribute defining features of the struct, such as its fields,
        validators, default values, etc. It's only of use for code that inspects struct
        definitions.

        :type: binobj.structures.StructMetadata

    .. versionchanged:: 0.5.0
        A Struct will compare equal to :data:`~binobj.fields.base.UNDEFINED` if
        and only if all of its fields are also undefined.

    .. versionchanged:: 0.7.1
        Removed the private-ish ``__components__`` and ``__validators__`` attributes.
        Field definitions, validators, and other metadata can be found in the
        new ``__binobj_struct__`` class attribute. However, it should be considered
        an implementation detail and is subject to change.
    """

    __binobj_struct__ = StructMetadata()

    def __init__(self, **values: Any):
        extra_keys = set(values.keys() - self.__binobj_struct__.components.keys())
        if extra_keys:
            raise errors.UnexpectedValueError(struct=self, name=extra_keys)

        self.__values__ = values

    def validate_contents(self) -> None:
        """Validate the stored values in this struct.

        :raise ~binobj.errors.ValidationError: Validation failed.

        .. versionadded:: 0.4.0
        """
        for f_name, validators in self.__binobj_struct__.field_validators.items():
            f_obj = self.__binobj_struct__.components[f_name]
            value = self[f_name]

            # First, invoke the validators defined on the field object.
            for instance_validator in f_obj.validators:
                instance_validator(value)

            # Second, invoke the validator methods for the field defined on this
            # Struct.
            for method_validator in validators:
                method_validator(self, f_obj, value)

        # Validate the entirety of the struct.
        for struct_validator in self.__binobj_struct__.struct_validators:
            struct_validator(self, typing.cast(StrDict, self))

    def to_stream(self, stream: BinaryIO, context: Any = None) -> None:
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

        for field in self.__binobj_struct__.components.values():
            value = field.compute_value_for_dump(all_fields)
            if value is not fields.NOT_PRESENT:
                field.to_stream(stream, value, context=context, all_fields=all_fields)

    def to_bytes(self, context: Any = None) -> bytes:
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

    def to_dict(self, keep_discardable: bool = False) -> MutableMapping[str, Any]:
        """Convert this struct into an ordered dictionary.

        The primary use for this method is converting a loaded :class:`Struct`
        into native Python types. As such, validation is *not* performed since
        that was done while loading.

        :param bool keep_discardable:
            If True, don't exclude fields marked with ``discard=True`` from the
            result.

            .. versionadded:: 0.6.1

        :rtype: collections.OrderedDict

        :raise MissingRequiredValueError:
            One or more fields don't have assigned values.

        .. versionchanged:: 0.6.0
            Fields with ``discard`` set are not included in the returned dict
            by default.

        .. versionchanged:: 0.3.0
            This now recursively calls :meth:`.to_dict` on all nested structs and
            arrays so that the returned dictionary is completely converted, not
            just the first level.
        """
        dct = collections.OrderedDict(
            (field.name, field.compute_value_for_dump(typing.cast(StrDict, self)))
            for field in self.__binobj_struct__.components.values()
            if keep_discardable or not field.discard
        )
        return recursive_to_dicts(dct)

    @classmethod
    def from_stream(
        cls: Type[TStruct],
        stream: BinaryIO,
        context: Any = None,
        init_kwargs: StrDict = None,
    ) -> TStruct:
        """Load a struct from the given stream.

        :param io.BufferedIOBase stream:
            The stream to load data from.
        :param context:
            Additional data to pass to the components'
            :meth:`~binobj.fields.base.Field.from_stream` methods. Subclasses must
            ignore anything they don't recognize.
        :param dict init_kwargs:
            Additional keyword arguments to pass to the struct's constructor,
            for subclasses that take additional arguments beyond the fields that
            comprise the struct. You can also use this to *override* field values;
            anything given in here takes precedence over loaded values.

            .. versionadded:: 0.7.0

        :return: The loaded struct.
        """
        if init_kwargs:
            results = typing.cast(MutableStrDict, copy.deepcopy(init_kwargs))
        else:
            results = {}

        for name, field in cls.__binobj_struct__.components.items():
            # We use setdefault() so we don't overwrite anything the caller may
            # have passed to us in `init_kwargs`.
            results.setdefault(name, field.from_stream(stream, context, results))

        instance = cls(**results)
        instance.validate_contents()

        for field in cls.__binobj_struct__.components.values():
            if field.discard:
                del instance[field.name]

        return instance

    @classmethod
    def from_bytes(
        cls: Type[TStruct],
        data: bytes,
        context: Any = None,
        exact: bool = True,
        init_kwargs: StrDict = None,
    ) -> TStruct:
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
        :param dict init_kwargs:
            Additional keyword arguments to pass to the struct's constructor,
            for subclasses that take additional arguments beyond the fields that
            comprise the struct. You can also use this to *override* field values;
            anything given in here takes precedence over loaded values.

            .. versionadded:: 0.7.0

        :return: The loaded struct.
        :raise ExtraneousDataError:
            ``exact`` is True and there's data left over at the end of the byte
            string.
        """
        stream = io.BytesIO(data)
        loaded_data = cls.from_stream(stream, context, init_kwargs)

        if exact and (stream.tell() < len(data) - 1):
            raise errors.ExtraneousDataError(
                "Read %d bytes, but there are %d in the input data."
                % (stream.tell() + 1, len(data)),
                offset=stream.tell(),
            )
        return loaded_data

    @classmethod
    def partial_load(
        cls: Type[TStruct],
        stream: BinaryIO,
        last_field: str = None,
        context: Any = None,
    ) -> TStruct:
        """Partially load this object, either until EOF or the named field.

        All fields up to and including the field named in ``last_field`` will be
        loaded from ``stream``.

        If ``last_field`` isn't given, as many complete fields as possible will
        be loaded from ``stream``. Any partially loaded fields will be discarded
        and the stream pointer will be reset to the end of the last complete
        field read.

        .. note::
            Because the struct is only partially loaded, struct-level validators
            are *not* executed. Individual fields still are.

        :param io.BufferedIOBase stream:
            The stream to load from.
        :param str last_field:
            The name of the last field to load in the object. If given, enough
            bytes for this and all previous fields *must* be present in the
            stream.
        :param context:
            Any object containing extra information to pass to the fields'
            :meth:`~binobj.fields.base.Field.from_stream` method.

        :return: The loaded struct.
        """
        if (
            last_field is not None
            and last_field not in cls.__binobj_struct__.components
        ):
            raise ValueError(
                "%s doesn't have a field named %r." % (cls.__name__, last_field)
            )

        result = {}  # type: MutableStrDict

        for field in cls.__binobj_struct__.components.values():
            offset = stream.tell()

            try:
                value = field.from_stream(stream, context=context, loaded_fields=result)
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
    def get_field(cls, stream: BinaryIO, name: str, context: Any = None) -> Any:
        """Return the value of a single field.

        If the field is at a fixed byte offset from the beginning of the struct,
        it'll be read directly.

        If the field isn't at a fixed offset from the beginning of the struct
        (e.g. a variable-length field occurs before it) then the entire struct
        up to and including this field must be read. Unfortunately, this means
        that unrelated validation errors can be thrown if other fields have
        problems.

        :param io.BufferedIOBase stream:
            The stream to read from. It's assumed that the stream pointer is
            positioned at the start of a struct. The stream pointer is returned
            to its original position even if an exception occurred.
        :param str name:
            The name of the field to retrieve.
        :param context:
            Optional. Any object containing extra information to pass to the
            :meth:`~binobj.fields.base.Field.from_stream` method of the field.
            For fields located at a variable offset, this will be passed to the
            :meth:`~binobj.fields.base.Field.from_stream` method of *each* field
            read.

        :return: The value of the field in the struct data.

        :raise UnexpectedEOFError:
            The end of the stream was reached before the requested field could
            be completely read.
        """
        if name not in cls.__binobj_struct__.components:
            raise ValueError("%s doesn't have a field named %r." % (cls.__name__, name))

        field = cls.__binobj_struct__.components[name]
        original_offset = stream.tell()

        # If the field is at a fixed offset from the beginning of the struct,
        # then we can read and return it directly.
        if field.offset is not None:
            try:
                stream.seek(original_offset + field.offset)
                return field.from_stream(stream, context, {})
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

    def partial_dump(
        self, stream: BinaryIO, last_field: Optional[str] = None, context: Any = None
    ) -> None:
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
            :meth:`~binobj.fields.base.Field.from_stream` methods.
        """
        data = self.__values__

        for field in self.__binobj_struct__.components.values():
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

            field.to_stream(stream, value, context)
            if field.name == last_field:
                return

    @classmethod
    def get_size(cls) -> Optional[int]:
        """Return the size of this struct in bytes, or ``None`` if there are
        variable-sized fields that can't be resolved.

        Do *not* use this on instances; use ``len(instance)`` instead.

        :return: The struct's size, in bytes.
        :rtype: int

        .. versionadded:: 0.3.0
        """
        sizes = [f.size for f in cls.__binobj_struct__.components.values()]

        # Don't try summing the sizes of the fields if anything in there isn't
        # an integer.
        if all(isinstance(s, int) for s in sizes):
            return sum(sizes)
        return None

    # Container methods

    def __getitem__(self, field_name: str) -> Any:
        if field_name not in self.__binobj_struct__.components:
            raise KeyError(
                "Struct %r has no field named %r." % (type(self).__name__, field_name)
            )
        return getattr(self, field_name)

    def __setitem__(self, field_name: str, value: Any) -> None:
        if field_name not in self.__binobj_struct__.components:
            raise KeyError(
                "Struct %r has no field named %r." % (type(self).__name__, field_name)
            )
        setattr(self, field_name, value)

    def __delitem__(self, field_name: str) -> Any:
        if field_name not in self.__binobj_struct__.components:
            raise KeyError(
                "Struct %r has no field named %r." % (type(self).__name__, field_name)
            )
        self.__values__.pop(field_name, None)

    def __iter__(self) -> Iterator[str]:
        for name, value in self.__values__.items():
            if value is not fields.UNDEFINED:
                yield name

    def __len__(self) -> int:
        size = 0
        for field in self.__binobj_struct__.components.values():
            if field.size is not None:
                size += field.size
            else:
                field_value = field.compute_value_for_dump(typing.cast(StrDict, self))
                size += len(field.to_bytes(field_value))

        return size

    def __eq__(self, other: Any) -> bool:
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

    def __bytes__(self) -> bytes:
        return self.to_bytes()

    def __repr__(self) -> str:
        return "%s(%s)" % (
            type(self).__qualname__,
            ", ".join("%s=%r" % kv for kv in self.__values__.items()),
        )
