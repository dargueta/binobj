"""Classes defining structures and unions."""

import collections
import collections.abc
import copy
import dataclasses
import io
import typing
import warnings
from typing import Any
from typing import BinaryIO
from typing import ClassVar
from typing import Dict
from typing import Iterator
from typing import List
from typing import Mapping
from typing import MutableMapping
from typing import Optional
from typing import overload
from typing import Sequence
from typing import Type
from typing import TypeVar

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


@dataclasses.dataclass
class StructMetadata:
    """Info about the :class:`.Struct` it belongs to, like its fields and validators.

    This class should be considered part of how Structs are implemented. It's only of
    use to people writing wrapper classes or otherwise enhancing the behavior of the
    default :class:`.Struct` class.

    .. versionadded:: 0.7.1

    .. versionchanged:: 0.10.0
        Arguments are now keyword-only.
    """

    name: str
    """The name of the class this metadata is for.

    .. versionadded:: 0.10.0
    """

    components: MutableMapping[str, fields.Field[Any]] = dataclasses.field(
        default_factory=dict
    )
    """A mapping of field names to the actual field object."""

    struct_validators: List[StructValidator] = dataclasses.field(default_factory=list)
    """A list of validators for this struct."""

    field_validators: MutableMapping[
        str, List[MethodFieldValidator]
    ] = dataclasses.field(default_factory=dict)
    """A mapping of field names to validators to execute for that field."""

    num_own_fields: int = 0
    """The number of fields defined in this class (i.e. excluding superclasses).

    .. versionadded:: 0.9.0
    """

    size_bytes: Optional[int] = 0
    """The total size of the struct in bytes, if it's a fixed value.

    This is only used for classes declared using PEP 526 type annotations and should
    otherwise be ignored.

    .. versionadded:: 0.9.0
    """

    argument_defaults: MutableStrDict = dataclasses.field(default_factory=dict)
    """A mapping of argument names or derived keys to their default values.

    Keys can take several forms:

    * A class name, followed by two underscores, then the field name. Class names are
      case-sensitive.
    * A single attribute name. This has the lowest precedence but the broadest reach.
    """

    def load_meta_options(self, meta: type) -> None:
        self.argument_defaults = dict(getattr(meta, "argument_defaults", {}))


def collect_assigned_fields(
    class_name: str,
    namespace: StrDict,
    class_metadata: StructMetadata,
    byte_offset: Optional[int],
) -> int:
    """Collect all fields defined by class variable assignment to a struct.

    Arguments:
        class_name (str):
            The name of the Struct class. Only used in error messages.
        namespace (dict):
            The class namespace, as passed to :meth:`StructMeta.__new__`.
        class_metadata (StructMetadata):
            The metadata object for the Struct being created.
        byte_offset (int):
            The byte offset to start at, typically 0 unless this struct inherits from
            another one. Will be ``None`` if the struct this class inherits from is of
            variable size.

    Returns
        int: The number of fields found.

    .. versionadded:: 0.9.0

    .. versionchanged:: 0.10.0
        The function now takes the entire class metadata as the first argument instead
        of just a mapping of the declared fields.
    """
    field_index = len(class_metadata.components)
    n_fields_found = 0

    # It's HIGHLY important that we don't accidentally bind the superclass' fields to
    # this struct. That's why we're iterating over ``namespace`` and adding the field
    # into the ``components`` dict *inside* the loop.
    for item_name, item in namespace.items():
        if not isinstance(item, fields.Field):
            continue
        if item_name in class_metadata.components:
            # Field was already defined in the superclass
            raise errors.FieldRedefinedError(struct=class_name, field=item)

        item.bind_to_container(class_metadata, item_name, field_index, byte_offset)
        if byte_offset is not None and item.has_fixed_size:
            byte_offset += typing.cast(int, item.size)
        else:
            byte_offset = None

        class_metadata.components[item_name] = item
        field_index += 1  # noqa: SIM113
        n_fields_found += 1  # noqa: SIM113

    return n_fields_found


def bind_validators_to_struct(namespace: StrDict, metadata: StructMetadata) -> None:
    """Find all defined validators and assign them to their fields.

    .. versionadded:: 0.9.0
    """
    for item in namespace.values():
        if not isinstance(item, decorators.ValidatorMethodWrapper):
            continue

        if item.field_names:
            # Attach this validator to each named field.
            for field_name in item.field_names:
                metadata.field_validators[field_name].append(item)
        else:
            # Validator doesn't define any fields, must be a validator for the entire
            # struct.
            metadata.struct_validators.append(item)


@overload
def recursive_to_dicts(item: "Struct") -> Dict[str, Any]:
    ...


@overload
def recursive_to_dicts(item: Mapping[K, V]) -> Dict[K, V]:
    ...


@overload
def recursive_to_dicts(item: Sequence[T]) -> List[T]:
    ...


def recursive_to_dicts(item):  # type: ignore[no-untyped-def]
    """Ensure that any nested structures are also converted to dictionaries.

    This is used when a :class:`Struct` is converted to a dictionary.

    :param item:
        Anything. If it's an unsupported type it'll get returned as is.
    """
    if isinstance(item, Struct):
        return item.to_dict()
    if isinstance(item, collections.abc.Mapping):
        return {recursive_to_dicts(k): recursive_to_dicts(v) for k, v in item.items()}
    if isinstance(item, collections.abc.Sequence) and not isinstance(
        item, (str, bytes, bytearray)
    ):
        return [recursive_to_dicts(v) for v in item]
    return item


class Struct:
    """An ordered collection of fields and other structures.

    .. versionchanged:: 0.5.0
        A Struct will compare equal to :data:`~binobj.fields.base.UNDEFINED` if and only
        if all of its fields are also undefined.

    .. versionchanged:: 0.7.1
        Removed the private-ish ``__components__`` and ``__validators__`` attributes.
        Field definitions, validators, and other metadata can be found in the new
        ``__binobj_struct__`` class attribute. However, it should be considered an
        implementation detail and is subject to change.

    .. versionchanged:: 0.10.0
        The ``__objclass__`` attribute is set on all fields.
    """

    __binobj_struct__: ClassVar[StructMetadata]
    """A class attribute defining features of the struct, such as its fields,
    validators, default values, etc.

    It's only of use for code that inspects struct definitions.
    """

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

        :param BinaryIO stream:
            The stream to write the serialized data into.
        :param context:
            Additional data to pass to this method. Subclasses must ignore anything they
            don't recognize.
        """
        self.validate_contents()

        # We can't pass `self` to all_fields because Structs can't be used with
        # dictionary expansion (e.g. **kwargs). It'd be a nasty surprise for
        # fields expecting a dictionary.
        all_fields = self.to_dict()

        for field in self.__binobj_struct__.components.values():
            value = field.compute_value_for_dump(all_fields, context)
            if value is not fields.NOT_PRESENT:
                field.to_stream(stream, value, context=context, all_fields=all_fields)

    def to_bytes(self, context: Any = None) -> bytes:
        """Convert the given data into bytes.

        :param context:
            Additional data to pass to this method. Subclasses must ignore anything they
            don't recognize.

        :return: The serialized data.
        :rtype: bytes
        """
        stream = io.BytesIO()
        self.to_stream(stream, context)
        return stream.getvalue()

    def to_dict(self, keep_discardable: bool = False) -> Dict[str, Any]:
        """Convert this struct into an ordered dictionary.

        The primary use for this method is converting a loaded :class:`Struct` into
        native Python types. As such, validation is *not* performed since that was done
        while loading.

        :param bool keep_discardable:
            If True, don't exclude fields marked with ``discard=True`` from the result.

        :rtype: Dict[str, Any]

        :raise MissingRequiredValueError:
            One or more fields don't have assigned values.

        .. versionchanged:: 0.3.0
            This now recursively calls :meth:`.to_dict` on all nested structs and arrays
            so that the returned dictionary is completely converted, not just the first
            level.

        .. versionchanged:: 0.6.0
            Fields with ``discard`` set are not included in the returned dict by
            default.

        .. versionchanged:: 0.6.1
            The ``keep_discardable`` argument was added.
        """
        dct = self._to_dict_whatever_possible()
        dct.update(
            {
                field.name: field.compute_value_for_dump(dct)
                for field in self.__binobj_struct__.components.values()
                if field.name not in dct
            }
        )

        if not keep_discardable:
            for field in self.__binobj_struct__.components.values():
                if field.discard:
                    del dct[field.name]

        return recursive_to_dicts(dct)

    def _to_dict_whatever_possible(self) -> MutableMapping[str, Any]:
        """Convert this struct to a dict, ignoring any errors.

        We use this to get values for all computed fields as well as any fields that
        have no dependencies and can serialize themselves (e.g. Bytes and sized int
        fields). This allows us to resolve forward references.
        """
        dct = {}

        for field in self.__binobj_struct__.components.values():
            try:
                dct[field.name] = field.compute_value_for_dump(
                    typing.cast(StrDict, self)
                )
            except errors.Error:
                continue

        return collections.ChainMap(dct, self)

    @classmethod
    def from_stream(
        cls: Type[TStruct],
        stream: BinaryIO,
        context: Any = None,
        init_kwargs: Optional[StrDict] = None,
    ) -> TStruct:
        """Load a struct from the given stream.

        :param BinaryIO stream:
            The stream to load data from.
        :param context:
            Additional data to pass to the components'
            :meth:`~binobj.fields.base.Field.from_stream` methods. Subclasses must
            ignore anything they don't recognize.
        :param dict init_kwargs:
            Additional keyword arguments to pass to the struct's constructor, for
            subclasses that take additional arguments beyond the fields that comprise
            the struct. You can also use this to *override* field values; anything given
            in here takes precedence over loaded values.

        :return: The loaded struct.

        .. versionadded:: 0.7.0
            The ``init_kwargs`` argument.
        """
        if init_kwargs:
            results = typing.cast(MutableStrDict, copy.deepcopy(init_kwargs))
        else:
            results = {}

        for name, field in cls.__binobj_struct__.components.items():
            # We use setdefault() so we don't overwrite anything the caller may have
            # passed to us in `init_kwargs`.
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
        init_kwargs: Optional[StrDict] = None,
    ) -> TStruct:
        """Load a struct from the given byte string.

        :param bytes data:
            A bytes-like object to get the data from.
        :param context:
            Additional data to pass to this method. Subclasses must ignore anything they
            don't recognize.
        :param bool exact:
            ``data`` must contain exactly the number of bytes required. If not all the
            bytes in ``data`` were used when reading the struct, throw an exception.
        :param dict init_kwargs:
            Additional keyword arguments to pass to the struct's constructor, for
            subclasses that take additional arguments beyond the fields that comprise
            the struct. You can also use this to *override* field values; anything given
            in here takes precedence over loaded values.

        :return: The loaded struct.
        :raise ExtraneousDataError:
            ``exact`` is True and there's data left over at the end of the byte string.

        .. versionadded:: 0.7.0
            The ``init_kwargs`` argument.
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
        last_field: Optional[str] = None,
        context: Any = None,
    ) -> TStruct:
        """Partially load this object, either until EOF or the named field.

        All fields up to and including the field named in ``last_field`` will be loaded
        from ``stream``.

        If ``last_field`` isn't given, as many complete fields as possible will be
        loaded from ``stream``. Any partially loaded fields will be discarded and the
        stream pointer will be reset to the end of the last complete field read.

        .. note::
            Because the struct is only partially loaded, struct-level validators are
            *not* executed. Individual fields still are.

        :param BinaryIO stream:
            The stream to load from.
        :param str last_field:
            The name of the last field to load in the object. If given, enough bytes for
            this and all previous fields *must* be present in the stream.
        :param context:
            Any object containing extra information to pass to the fields'
            :meth:`~binobj.fields.base.Field.from_stream` method.

        :return: The loaded struct.
        """  # noqa: D401
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

                # Hit EOF in the middle of reading a field. Since the caller didn't
                # specify how far we should read, this isn't an error. Go back to the
                # beginning of this field and return.
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

        If the field is at a fixed byte offset from the beginning of the struct, it'll
        be read directly.

        If the field isn't at a fixed offset from the beginning of the struct (e.g. a
        variable-length field occurs before it) then the entire struct up to and
        including this field must be read. Unfortunately, this means that unrelated
        validation errors can be thrown if other fields have problems.

        :param BinaryIO stream:
            The stream to read from. It's assumed that the stream pointer is positioned
            at the start of a struct. The stream pointer is returned to its original
            position even if an exception occurred.
        :param str name:
            The name of the field to retrieve.
        :param context:
            Optional. Any object containing extra information to pass to the
            :meth:`~binobj.fields.base.Field.from_stream` method of the field. For
            fields located at a variable offset, this will be passed to the
            :meth:`~binobj.fields.base.Field.from_stream` method of *each* field read.

        :return: The value of the field in the struct data.

        :raise UnexpectedEOFError:
            The end of the stream was reached before the requested field could be
            completely read.
        """
        if name not in cls.__binobj_struct__.components:
            raise ValueError("%s doesn't have a field named %r." % (cls.__name__, name))

        field = cls.__binobj_struct__.components[name]
        original_offset = stream.tell()

        # If the field is at a fixed offset from the beginning of the struct, then we
        # can read and return it directly.
        if field.offset is not None:
            try:
                stream.seek(original_offset + field.offset)
                return field.from_stream(stream, context, {})
            finally:
                stream.seek(original_offset)

        # If we get here then the field is *not* at a fixed offset from the beginning of
        # the struct and we have to read everything up to it. This can unfortunately
        # result in validation errors if there is data before the desired field that's
        # invalid.
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

        If ``last_field`` isn't given, as many fields will be serialized as possible up
        to the first missing one.

        :param BinaryIO stream:
            The stream to dump into.
        :param str last_field:
            The name of the last field in the object to dump.
        :param context:
            Any object containing extra information to pass to the fields'
            :meth:`~binobj.fields.base.Field.from_stream` methods.
        """  # noqa: D401
        data = self.__values__

        for field in self.__binobj_struct__.components.values():
            value = data.get(field.name, field.default)
            if value is fields.UNDEFINED:
                # Field is missing from the dump data. If the caller wants us to dump
                # only the fields that're defined, we can bail out now.
                if last_field is None:
                    return
                if field.required:
                    # Caller wants us to dump up to and including ``last_field`` so we
                    # need to crash.
                    raise errors.MissingRequiredValueError(field=field)

            field.to_stream(stream, value, context)
            if field.name == last_field:
                return

    @classmethod
    def get_size(cls) -> Optional[int]:
        """Return the size of this struct in bytes, if possible.

        If there are variable-sized fields that can't be resolved, this function returns
        ``None`` instead.

        Do *not* use this on instances; use ``len(instance)`` instead.

        :return: The struct's size, in bytes.
        :rtype: int

        .. versionadded:: 0.3.0
        """
        field_objects = cls.__binobj_struct__.components.values()
        try:
            return sum(f.get_expected_size({}) for f in field_objects)
        except (errors.UndefinedSizeError, errors.MissingRequiredValueError):
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
        current_fields = self._to_dict_whatever_possible()

        for field in self.__binobj_struct__.components.values():
            if field.has_fixed_size:
                size += typing.cast(int, field.size)
            else:
                try:
                    size += field.get_expected_size(current_fields)
                except errors.Error:
                    field_value = field.compute_value_for_dump(current_fields)
                    size += len(field.to_bytes(field_value))

        return size

    def __eq__(self, other: Any) -> bool:
        # Allow comparison to UNDEFINED. The result is True if all fields in this
        # struct are undefined, False otherwise.
        if other is fields.UNDEFINED:
            warnings.warn(
                "Comparing a struct to UNDEFINED to see if all its fields are undefined"
                " is deprecated. Starting version 1.0 this will always return False.",
                DeprecationWarning,
                stacklevel=2,
            )
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

    def __init_subclass__(cls) -> None:
        # Build a list of all the base classes that appear to be Structs.
        struct_bases = [
            b for b in cls.__bases__ if issubclass(b, Struct) and b is not Struct
        ]

        if len(struct_bases) > 1:
            raise errors.MultipleInheritanceError(struct=cls.__name__)

        metadata = StructMetadata(name=cls.__name__)
        namespace = vars(cls)

        if struct_bases:
            # Build a dictionary of all of the fields in the parent struct first, then
            # add in the fields defined in this struct.
            base = struct_bases[0]

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
            byte_offset = base.get_size()
        else:
            # Else: This struct doesn't inherit from another struct, so we're starting
            # at offset 0. There are no field or struct validators to copy.
            byte_offset = 0

        metadata.field_validators.update(
            {
                name: []
                for name, obj in namespace.items()
                if isinstance(obj, fields.Field)
            }
        )

        # Load any construction options the caller may have defined.
        if hasattr(cls, "Meta"):
            metadata.load_meta_options(cls.Meta)

        # Enumerate the declared fields and bind them to this struct.
        metadata.num_own_fields = collect_assigned_fields(
            cls.__name__, namespace, metadata, byte_offset
        )
        bind_validators_to_struct(namespace, metadata)

        cls.__binobj_struct__ = metadata

        # Set __objclass__ on all fields to aid type introspection. The `inspect` module
        # uses this as an aid.
        for field in metadata.components.values():
            field.__objclass__ = cls

        super().__init_subclass__()
