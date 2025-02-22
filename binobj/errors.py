"""Errors for the binobj package."""

from __future__ import annotations

import typing
from typing import Any
from typing import Optional
from typing import TypeVar
from typing import Union

import more_itertools as m_iter


if typing.TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Iterable

    from binobj.fields import Field
    from binobj.structures import Struct
    from binobj.typedefs import FieldOrName
    from binobj.typedefs import StructOrName


T = TypeVar("T")


__all__ = [
    "ArraySizeError",
    "ConfigurationError",
    "DeserializationError",
    "Error",
    "ExtraneousDataError",
    "FieldRedefinedError",
    "FieldReferenceError",
    "IllegalOperationError",
    "ImmutableFieldError",
    "MissingRequiredValueError",
    "MultipleInheritanceError",
    "SerializationError",
    "UndefinedSizeError",
    "UnexpectedEOFError",
    "UnexpectedValueError",
    "UnserializableValueError",
    "ValidationError",
    "ValueSizeError",
]


class Error(Exception):
    """Base class for all binobj errors.

    Do not throw this exception directly.
    """

    def __init__(self, message: Optional[str] = None, *args: object):
        # If there is no error message, use the first line of the docstring.
        if message is None and hasattr(self, "__doc__") and self.__doc__:
            message = self.__doc__.splitlines()[0]
        super().__init__(message, *args)


class ConfigurationError(Error):
    """A field, struct, or other object was misconfigured.

    At least one of the ``field``, ``struct``, or ``obj`` keyword arguments must be
    passed to the constructor.

    :param str message:
        Optional. A description of what's wrong. If not given, a generic error message
        will be chosen depending on which of the ``field``, ``struct``, or ``obj``
        keyword arguments is passed.
    :param field:
        The misconfigured :class:`~binobj.fields.base.Field` or its name.
    :param struct:
        The misconfigured :class:`~binobj.structures.Struct` or its name.
    :param obj:
        If the misconfigured object is neither a field nor a struct, pass it or its name
        here.

    :raise ValueError:
        None of the ``field``, ``struct``, or ``obj`` keyword arguments were passed.

    .. versionadded:: 0.3.0
        The ``struct`` and ``obj`` arguments.
    """

    field: Optional[FieldOrName]
    struct: Optional[StructOrName]
    obj: Any

    def __init__(
        self,
        message: Optional[str] = None,
        *,
        field: Optional[FieldOrName] = None,
        struct: Optional[StructOrName] = None,
        obj: object = None,
    ):
        if not (field or struct or obj):
            raise ValueError(
                "At least one of `field`, `struct`, or `obj` must be passed to the"
                " constructor."
            )

        if not message:
            if field:
                if struct:
                    message = "Field {f!r} in struct {s!r} was misconfigured."
                else:
                    message = "The field {f!r} was misconfigured."
            elif struct:
                message = "The struct {s!r} was misconfigured."
            else:
                message = "The object {o!r} was misconfigured."

            message = message.format(f=field, s=struct, o=obj)

        super().__init__(message)
        self.field = field
        self.struct = struct
        self.obj = obj


class SerializationError(Error):
    """An error occurred while serializing data.

    :param str message:
        An error message explaining the problem.
    :param ~binobj.structures.Struct struct:
        The struct that contains the field that failed to be serialized.
    :param ~binobj.fields.base.Field field:
        The field that failed to be serialized.
    :param value:
        The value that caused the crash.
    """

    def __init__(
        self,
        message: Optional[str] = None,
        *,
        struct: Optional[Struct] = None,
        field: Optional[FieldOrName] = None,
        value: Optional[T] = None,
    ):
        super().__init__(message)
        self.struct = struct
        self.field = field
        self.value = value


class DeserializationError(Error):
    """An error occurred while deserializing data.

    :param str message:
        An error message explaining the problem.
    :param ~binobj.fields.base.Field field:
        The field that failed to load.
    :param bytes data:
        The raw data that was read that led to the crash.
    :param int offset:
        The offset into the data stream where the crash occurred.
    """

    def __init__(
        self,
        message: Optional[str] = None,
        *,
        field: Optional[Field[Any]] = None,
        data: Optional[bytes] = None,
        offset: Optional[int] = None,
    ):
        super().__init__(message)
        self.field = field
        self.data = data
        self.offset = offset


class ValidationError(Error):
    """Validation failed for one or more fields.

    :param str message:
        An error message explaining the problem.
    :param ~binobj.fields.base.Field field:
        The field that failed validation.
    :param value:
        The invalid value.
    """

    def __init__(
        self, message: Optional[str] = None, *, field: Field[T], value: Optional[T]
    ):
        if not message:
            message = f"Invalid value for {field}: {value!r}"

        super().__init__(message)
        self.field = field
        self.value = value


class FieldReferenceError(Error):
    """An error occurred while computing a field reference.

    :param str message:
        Optional. A more detailed error message, if desired.
    :param str field:
        The name of the field that failed to be referenced.
    """

    def __init__(self, message: Optional[str] = None, *, field: str):
        if not message:
            message = f"Attempted to reference a missing or undefined field: {field!r}"

        super().__init__(message)
        self.field = field


class IllegalOperationError(Error):
    """The attempted operation is disallowed.

    .. versionadded:: 0.4.1
    """


################################################################################


class ImmutableFieldError(IllegalOperationError):
    """Cannot assign to an immutable or computed field.

    :param ~binobj.fields.base.Field field:
        The field an attempt was made to be assigned to.


    .. versionadded:: 0.4.1
    .. versionadded:: 0.6.1
        The ``field`` argument.
    """

    def __init__(self, *, field: Optional[Field[Any]] = None):
        message: Optional[str]
        if field is not None:
            message = f"Cannot assign to immutable field: {field!r}"
        else:
            message = None

        super().__init__(message)
        self.field = field


class MultipleInheritanceError(ConfigurationError):
    """A Struct can't inherit from more than one Struct.

    This restriction is in place because the field ordering could be non-intuitive given
    Python's MRO.

    .. versionadded:: 0.3.0
    """


class FieldRedefinedError(ConfigurationError):
    """A struct has a field already defined in a parent class.

    :param str struct:
        The name of the struct that has the redefined field.
    :param field:
        The :class:`~binobj.fields.base.Field` that's been redefined, or its name.

    .. versionadded:: 0.3.0
    """

    def __init__(self, *, struct: str, field: FieldOrName):
        super().__init__(
            f"Struct {struct} defines field {field!r}, which is already defined in its"
            " parent class.",
            struct=struct,
            field=field,
        )


class UndefinedSizeError(ConfigurationError):
    """The size of the field couldn't be determined, possibly due to misconfiguration.

    :param field:
        The :class:`~binobj.fields.base.Field` that's missing its size, or the name of
        that field.

    .. versionadded:: 0.3.1
    """

    def __init__(self, *, field: FieldOrName):
        super().__init__(
            f"Size of field {field} couldn't be determined. The field might not have"
            " had its `size` set, or a variable-sized field has a bug.",
            field=field,
        )


class NoDefinedFieldsError(ConfigurationError):
    """The struct has no defined fields.

    .. versionadded:: 0.9.0
    """

    def __init__(self, *, struct: StructOrName):
        super().__init__(f"The struct {struct!r} has no defined fields.", struct=struct)


class MixedDeclarationsError(ConfigurationError):
    """The class declares fields with both PEP 526 and assignments; only one is allowed.

    Aside from mixing both kinds of declarations, this will also happen when a user
    declares their struct with :func:`~binobj.pep526.dataclass` but uses the old form of
    assignment-based field definitions.

    .. versionadded:: 0.9.0
    """


class InvalidTypeAnnotationError(ConfigurationError):
    """The type annotation for a field is invalid.

    .. versionadded:: 0.9.0
    """

    annotation: Any
    """The offending type annotation."""

    def __init__(self, *, field: FieldOrName, annotation: object):
        message = (
            f"The type annotation for field {field!r} is invalid. For example, you"
            " can't use typing.Union[X, Y] to emulate binobj.fields.Union. The"
            f" annotation is: {annotation!r}"
        )
        super().__init__(message, field=field)
        self.annotation = annotation


class CannotDetermineNullError(ConfigurationError):
    """The `null_value` for this field couldn't be determined when loading.

    .. versionadded:: 0.9.0
    """

    def __init__(self, *, field: Field[Any]):
        super().__init__(
            f"Passing `DEFAULT` for `null_value` of unsized field {field.name!r} makes"
            " it impossible to determine what None should be and would result in"
            " unpredictable behavior.",
            field=field,
        )


class BuggyFieldImplementationError(ConfigurationError):
    """There's a bug in an implementation of a field.

    .. versionadded:: 0.11.0
    """

    def __init__(self, message: str, *, field: Field[Any]):
        field_type = type(field)
        super().__init__(
            f"Field type {field_type!r} has a bug in its implementation: {message}",
            field=field,
        )


class UnserializableValueError(SerializationError):
    """The value couldn't be serialized.

    :param ~binobj.fields.base.Field field:
        The field that failed to serialize the given value.
    :param value:
        The value that can't be serialized.
    :param str reason:
        Optional. The reason for the failure.
    """

    def __init__(
        self, *, field: Field[T], value: Optional[T], reason: Optional[str] = None
    ):
        if reason is not None:
            message = f"{field} can't serialize value: {reason}"
        else:
            message = (
                f"{field} can't serialize value of type {type(value).__qualname__}."
            )
        super().__init__(message, field=field, value=value)


class MissingRequiredValueError(SerializationError):
    """No value was passed for a required field.

    :param field:
        The missing field, or its name.
    """

    def __init__(self, *, field: FieldOrName):
        super().__init__(f"Missing required value for field: {field}", field=field)


class UnexpectedValueError(SerializationError):
    """The data to dump has unexpected fields.

    :param ~binobj.structures.Struct struct:
        The struct performing the serialization.
    :param name:
        Either a string or an iterable of strings, each being the name of a field that
        was unexpected. Don't pass :class:`~binobj.fields.base.Field` instances.
    """

    def __init__(self, *, struct: Struct, name: Union[str, Iterable[str]]):
        self.names = set(m_iter.always_iterable(name))

        msg = (
            f"{len(self.names)} unrecognized field(s) given to"
            f" {type(struct).__qualname__} for serialization: "
            + ", ".join(repr(f) for f in sorted(self.names))
        )

        super().__init__(msg, struct=struct)


class ValueSizeError(UnserializableValueError):
    """The value can't be serialized because it doesn't fit into the field.

    :param ~binobj.fields.base.Field field:
        The field that failed to serialize the given value.
    :param value:
        The value that's the wrong size.
    """

    def __init__(self, *, field: Field[Any], value: object):
        super().__init__(
            reason=f"Value doesn't fit into {field.size!r} bytes.",
            field=field,
            value=value,
        )


class ArraySizeError(SerializationError):
    """The array can't be serialized because there are too many or too few items.

    :param ~binobj.fields.base.Field field: The field that failed to be serialized.
    :param int n_expected: The expected number of items in the field.
    :param int n_given:
        Optional. The actual number of items given to the field for serialization.
    """

    def __init__(
        self, *, field: Field[Any], n_expected: int, n_given: Optional[int] = None
    ):
        if n_given is not None:
            if n_given > n_expected:
                message = f"Expected {n_expected} values, got at least {n_given}."
            else:
                message = f"Expected {n_expected} values, got {n_given}."
        else:
            message = f"Expected {n_expected} values."

        super().__init__(message, field=field)
        self.n_expected = n_expected
        self.n_given = n_given


class UnexpectedEOFError(DeserializationError):
    """Hit EOF while reading, but expected more data.

    :param ~binobj.fields.base.Field field:
        The field that failed to be deserialized.
    :param int size:
        The number of bytes that were attempted to be read.
    :param int offset:
        The offset into the input stream/string where the error was encountered, in
        bytes.
    """

    def __init__(self, *, field: Optional[Field[Any]], size: int, offset: int):
        super().__init__(
            f"Unexpected EOF while trying to read {size} bytes at offset {offset}.",
            field=field,
            offset=offset,
        )

        self.size = size


class ExtraneousDataError(DeserializationError):
    """Extra bytes were found at the end of the input after deserialization."""
