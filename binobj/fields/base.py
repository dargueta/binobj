"""Base classes and definitions common to all Fields."""

from __future__ import annotations

import abc
import enum
import functools
import io
import os
import typing
import warnings
from typing import Any
from typing import BinaryIO
from typing import Callable
from typing import ClassVar
from typing import Generic
from typing import Optional
from typing import overload
from typing import TypeVar
from typing import Union

import more_itertools as m_iter
from typing_extensions import Self

from binobj import errors
from binobj import helpers


if typing.TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Collection
    from collections.abc import Iterable

    from binobj.structures import Struct
    from binobj.structures import StructMetadata
    from binobj.typedefs import FieldValidator
    from binobj.typedefs import StrDict


__all__ = ["DEFAULT", "NOT_PRESENT", "UNDEFINED", "Field"]


class _Default(enum.Enum):
    token = 0


class _Undefined(enum.Enum):
    token = 0


class _NotPresent(enum.Enum):
    token = 0


UNDEFINED = _Undefined.token
"""A sentinel value used to indicate that a setting or field is undefined."""


DEFAULT = _Default.token
"""A sentinel value used to indicate that the default value of a setting should be used.

We need this because sometimes ``None`` is a valid value for that setting.
"""


NOT_PRESENT = _NotPresent.token
"""A sentinel value used to indicate that a field is not present.

.. versionadded:: 0.4.5
"""

T = TypeVar("T")


class Field(Generic[T]):
    r"""The base class for all struct fields.

    :param str name:
        The name of the field.

        .. versionchanged:: 0.11.0

            Passing a value for this will throw a :class:`ConfigurationError` for
            fields declared in a normal class if it doesn't match the existing name.
            Only use this argument if you're building a struct programmatically.
    :param const:
        A constant value this field is expected to take. It will always have this value
        when dumped, and will fail validation if the field isn't this value when loaded.
        Useful for reserved fields and file tags.

        This argument *must* be of the same type as the field, i.e. it must be a string
        for a :class:`~binobj.fields.stringlike.String`, an integer for an
        :class:`~binobj.fields.numeric.Integer`, and so on.
    :param default:
        The default value to use if a value for this field isn't passed to the struct
        for serialization, or (deprecated) a callable taking no arguments that will
        return a default value.

        This argument *must* be of the same type as the field, i.e. it must be a string
        for a :class:`~binobj.fields.stringlike.String`, an integer for an
        :class:`~binobj.fields.numeric.Integer`, and so on.

        .. deprecated:: 0.11.0
            Do not pass a factory function to this argument. Use ``factory`` instead.
    :param callable factory:
        A callable taking no arguments that returns a default value for this field.
    :param bool discard:
        When deserializing, don't include this field in the returned results. This means
        that you won't be able to use the value for anything later. For example, if you
        need to reference it in a ``present`` function like so::

            name_size = fields.UInt16(discard=True)
            filename = fields.StringZ(encoding="utf-8")
            _filename_padding = fields.Bytes(
                const=b"\0", discard=True, present=lambda f, *_: f["name_size"] % 2
            )

        this will crash with a :class:`KeyError` because ``name_size`` was discarded.
    :param null_value:
        Either a byte string or a value to use to represent ``None`` in serialized data.

        When loading, the returned value will be ``None`` if this exact sequence of
        bytes is encountered. If not given, the field is considered "not nullable" and
        any attempt to assign ``None`` to it will result in a crash upon serialization.
    :param size:
        Optional. The size of the field. This can be a number of things:

        * An integer constant. The field will always be the same size, no matter what
          value is given to it.
        * Another :class:`.Field` object. That field gives the size of this field, in
          bytes.
        * A string naming another field. It's equivalent to passing in a :class:`.Field`
          instance, except used for references in the same class or a field defined in
          the superclass.
    :param validate:
        A callable or list of callables that validates a given value for this field. The
        callable(s) will always be passed the deserialized value, so a validator for an
        :class:`~binobj.fields.numeric.Integer` field will always be passed an integer,
        a :class:`~binobj.fields.stringlike.String` validator will always be passed a
        string, and so on.
    :param callable present:
        Optional. A callable that, when called with the struct as its argument,
        returns a boolean indicating if this field is "present" and should be loaded or
        dumped. For example, if we have a ``flags`` field that's a bitmap indicating
        what fields come next, we could have something like this::

            flags = fields.UInt16()
            foo = fields.StringZ(present=lambda v, *_: v["flags"] & 0x8000)
            bar = fields.StringZ(present=lambda v, *_: v["flags"] & 0x4000)

        Thus, if and only if ``flags`` has bit 15 set, ``foo`` will be read from the
        stream next. If ``flags`` has bit 15 clear, ``foo`` will be assigned the field's
        :attr:`not_present_value` (defaults to :data:`NOT_PRESENT`).

        The callable takes three positional arguments:

        - A dict of the fields that have already been loaded or are about to be dumped.
        - The ``context`` object passed to :meth:`from_stream` or :meth:`to_stream`.
        - When loading, the stream being loaded from. The stream pointer MUST be reset
          to its original position before the function returns.

    :param not_present_value:
        A custom value to return if a field is missing when loading (see the ``present``
        argument). It can be ``None`` or match the datatype of the field, i.e. a string
        for a :class:`~binobj.fields.stringlike.String`, an integer for an
        :class:`~binobj.fields.numeric.Integer`, and so on. If not given, defaults to
        :data:`NOT_PRESENT`.

    .. attribute:: index

        The zero-based index of the field in the struct.

        :type: int

    .. attribute:: offset

        The zero-based byte offset of the field in the struct. If the offset can't be
        computed (e.g. it's preceded by a variable-length field), this will be ``None``.

        :type: int

    .. versionadded:: 0.4.5
        The ``present`` argument.

    .. versionchanged:: 0.8.0
        This now inherits from :class:`typing.Generic`.

    .. versionadded:: 0.9.0

    * The ``not_present_value`` argument.
    * ``size`` has full support for :class:`Field`\s and field name values. This
      used to be only supported by some fields, with others left out by accident.

    .. versionchanged:: 0.9.0
        ``null_value`` can now also be a deserialized value. For example, you could pass
        r"\\N" for a string or 0 for an integer.

    .. deprecated:: 0.9.0
        Passing :data:`DEFAULT` to ``null_value`` for unsized fields such as
        :class:`~binobj.fields.stringlike.StringZ` is deprecated and will trigger an
        error in the future. This resolves the asymmetric behavior where using
        :data:`DEFAULT` throws an error when dumping but happily loads whatever's next
        in the stream when loading.

    .. versionadded:: 0.11.0
        The ``factory`` argument.

    .. deprecated:: 0.11.0
        Passing a factory function to ``default`` is now deprecated. Use ``factory``
        instead.
    """

    __overrideable_attributes__: ClassVar[Collection[str]] = ()
    """The names of attributes that can be configured using the containing struct's
    ``Meta`` class options.
    """

    __explicit_init_args__: frozenset[str]
    """The names of arguments that were explicitly passed to the constructor."""

    __objclass__: type[Struct]
    """The :class:`~binobj.structures.Struct` class that this ``Field`` is bound to.

    This is the class object, not a particular instance of the class.
    """

    name: str
    """The name of the field.

    **Technical Note:**
    This attribute can only be ``None`` if the field was created without passing a value
    for ``name`` to the constructor *and* the field has never been bound to a struct.
    Since this is highly unlikely in normal usage, this attribute is declared as ``str``
    rather than ``Optional[str]``.
    """

    const: Union[T, _Undefined]
    """The fixed value of a field, if applicable.

    This is mostly useful for fields that act as `magic numbers`_ or reserved fields
    in a struct that should be set to nulls.

    .. _magic numbers: https://en.wikipedia.org/wiki/Magic_number_(programming)
    """

    discard: bool
    """If True, indicates that a field should be discarded when read.

    This is best used for filler fields that are of no use to the application but are
    nonetheless important to ensure the proper layout of the struct.
    """

    _default: Union[T, None, _Undefined]
    """The default dump value for the field if the user doesn't pass a value in."""

    _compute_fn: Optional[Callable[[Field[T], StrDict], Optional[T]]]

    def __new__(cls, *_args: object, **kwargs: object) -> Self:
        """Create a new instance, recording which keyword arguments were passed in.

        Recording the explicit arguments is necessary so that a field can use the
        fallback values its container class gives for anything else.
        """
        instance = super().__new__(cls)
        instance.__explicit_init_args__ = frozenset(kwargs.keys())
        return instance

    def __init__(  # noqa: PLR0913
        self,
        *,
        name: Optional[str] = None,
        const: Union[T, _Undefined] = UNDEFINED,
        default: Union[T, None, Callable[[], Optional[T]], _Undefined] = UNDEFINED,
        factory: Optional[Callable[[], Optional[T]]] = None,
        discard: bool = False,
        null_value: Union[bytes, _Default, _Undefined, T] = UNDEFINED,
        size: Union[int, str, Field[int], None] = None,
        validate: Union[FieldValidator, Iterable[FieldValidator]] = (),
        present: Callable[[StrDict, Any, Optional[BinaryIO]], bool] = (lambda *_: True),
        not_present_value: Union[T, None, _NotPresent] = NOT_PRESENT,
    ):
        self.const = const
        self.discard = discard
        self.null_value = null_value
        self.present = present
        self.factory = factory
        self.not_present_value = not_present_value
        self.validators = [
            functools.partial(v, self) for v in m_iter.always_iterable(validate)
        ]

        if factory is not None and default is not UNDEFINED:
            raise errors.ConfigurationError(
                "Do not pass values for both `default` and `factory`.", field=self
            )

        if default is UNDEFINED and const is not UNDEFINED:
            # If no default is given but `const` is, set the default value to `const`.
            self._default = const
        elif callable(default):
            warnings.warn(
                "Passing a callable to `default` is deprecated. Use `factory` instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            self._default = UNDEFINED
            self.factory = default
        else:
            self._default = default

        # These attributes are typically set by the struct containing the field after
        # the field's instantiated.
        self.name = typing.cast(str, name)
        self.index = typing.cast(int, None)
        self.offset: Optional[int] = None
        self._compute_fn = None

        if size is not None or const is UNDEFINED:
            self._size = size
        else:
            self._size = self._size_for_value(const)

    @property
    def size(self) -> Union[int, str, Field[int], None]:
        """The size of this field, in bytes.

        If the field is of variable size, such as a null-terminated string, this will be
        ``None``. Builtin fields set this automatically if ``const`` is given but you'll
        need to implement :meth:`_size_for_value` in custom fields.
        """
        # TODO (dargueta): This return value is horrific. Rework it if possible.
        return self._size

    @property
    def has_fixed_size(self) -> bool:
        """Does this field have a fixed size?

        .. versionadded:: 0.9.0
        """
        return isinstance(self.size, int)

    def bind_to_container(
        self,
        struct_info: StructMetadata,
        name: str,
        index: int,
        offset: Optional[int] = None,
    ) -> None:
        """Bind this field to a Struct and apply any predefined defaults.

        :param binobj.structures.StructMetadata struct_info:
            The metadata object describing the Struct this field will be bound into.
        :param str name:
            The name of this field.
        :param int index:
            The index of this field in the container.
        :param int offset:
            The byte offset of this field in the container, or ``None`` if unknown. This
            is usually equal to the sum of the sizes of the fields preceding this one in
            the container.

        .. versionchanged:: 0.10.0
            Added the ``struct_info`` parameter.
        """
        maybe_assign_name(self, name)
        self.index = index
        self.offset = offset

        for argument_name in self.__overrideable_attributes__:
            if argument_name in self.__explicit_init_args__:
                # This argument was passed in to the constructor directly and any
                # defaults specified by the struct's metainformation should be ignored.
                continue

            # If we get here then no explicit value was passed in for the argument, and
            # we need to see if there's a default specified at the struct level.
            #
            # First, we check to see if there's a default value provided using this
            # field type's class AND argument name. For example, for an Int16 field we
            # want to check for a default value for the "endian" argument by searching
            # in the struct-level defaults for "Int16__endian".
            #
            # If we don't find a default specific to the type, we'll try to find a
            # default value not constrained to the type (i.e. will match all arguments
            # across all fields with the given name).
            typed_default_name = type(self).__name__ + "__" + argument_name
            if typed_default_name in struct_info.argument_defaults:
                # Found a type-specific default value
                setattr(
                    self,
                    argument_name,
                    struct_info.argument_defaults[typed_default_name],
                )
            elif argument_name in struct_info.argument_defaults:
                # Found a generic default value
                setattr(
                    self, argument_name, struct_info.argument_defaults[argument_name]
                )
            # Else: struct doesn't define a default value for this argument.

    def compute_value_for_dump(
        self,
        all_values: StrDict,
        context: object = None,
    ) -> Union[T, None, _NotPresent]:
        """Calculate the value for this field upon dumping.

        :param dict all_values:
            The dictionary of all the field data that's about to be dumped.
        :param context:
            The context object passed to the containing Struct's ``to_bytes()`` or
            ``to_stream()`` method.

            .. versionadded:: 0.11.0

        :return:
            The value the dumper will use for this field, or :data:`NOT_PRESENT` if the
            field shouldn't be serialized. It *will not* return
            :attr:`.not_present_value` in this case, as the field should not be dumped
            at all.

        :raise MissingRequiredValueError:
            No value could be derived for this field. It's missing in the input data,
            there's no default defined, and it doesn't have a compute function defined
            either.

        .. versionadded:: 0.3.1

        .. versionchanged:: 0.8.0
            If ``default`` is given by a callable and that callable returns
            :data:`UNDEFINED`, it will throw :class:`~.errors.MissingRequiredValueError`
            instead of returning :data:`UNDEFINED`.

        .. versionchanged:: 0.11.0
            * The ``context`` argument was added, and is now passed to the
              :attr:`present` callable.
            * ``present()`` is now always called, even if the value of the field is set.
              Before, if a field had a value explicitly set, it would be included in the
              output even if present() would've returned False.
        """
        if self.name in all_values:
            # The value is already set in the struct so we don't need to do anything.
            value_to_dump = all_values[self.name]
        elif self._default is not UNDEFINED:
            # The value is *not* set in the struct. Either this field must have a
            # default value, or it must be a computed field. Check for default values
            # here.
            value_to_dump = self.default
        elif self._compute_fn is not None:
            # This is a computed field.
            value_to_dump = self._compute_fn(self, all_values)
        else:
            # We were unable to find a value for this field.
            value_to_dump = UNDEFINED

        if value_to_dump is NOT_PRESENT or not self.present(all_values, context, None):
            return NOT_PRESENT
        if value_to_dump is UNDEFINED:
            # No default value and this isn't a computed field either.
            raise errors.MissingRequiredValueError(field=self)
        return value_to_dump  # type: ignore[no-any-return]

    def computes(self, method: Callable[[Field[T], StrDict], Optional[T]]) -> None:
        """Decorator that marks a function as computing the value for a field.

        You can use this for automatically assigning values based on other fields. For
        example, suppose we have this struct::

            class MyStruct(Struct):
                n_numbers = UInt8()
                numbers = Array(UInt8(), count=n_numbers)

        This works great for loading, but when we're dumping we have to pass in a value
        for ``n_numbers`` explicitly. We can use the ``computes`` decorator to relieve
        us of that burden::

            class MyStruct(Struct):
                n_numbers = UInt8()
                numbers = Array(UInt8(), count=n_numbers)

                @n_numbers.computes
                def _assign_n_numbers(self, all_fields):
                    return len(all_fields['numbers'])

        Some usage notes:

        * The computing function will *not* be called if

          * A value is explicitly set for the field by the calling code.
          * The field has a ``default`` or ``const`` value.

        * Computed fields are executed in the order that the fields are dumped, so a
          computed field must *not* rely on the value of another computed field
          occurring after it.

        .. versionadded:: 0.3.0
        """
        if self._compute_fn:
            raise errors.ConfigurationError(
                f"Can't define two computing functions for field {self!r}.", field=self
            )
        if self.const is not UNDEFINED:
            raise errors.ConfigurationError(
                "Cannot set compute function for a const field.", field=self
            )

        self._compute_fn = method

    @property
    def is_computed_field(self) -> bool:
        """Indicate if this field is computed from the value of other fields.

        Computed fields cannot have their values set directly. Attempting to do so will
        throw an :class:`~binobj.errors.ImmutableFieldError`.
        """
        return self._compute_fn is not None

    @property
    def allow_null(self) -> bool:
        """Indicate if ``None`` an acceptable value for this field.

        :type: bool
        """
        return self.null_value is not UNDEFINED

    @property
    def default(self) -> Union[T, None, _Undefined]:
        """The default value of this field, or :data:`UNDEFINED`.

        .. versionchanged:: 0.6.1
            If no default is defined but ``const`` is, this property returns the value
            for ``const``.
        """
        if self.factory:
            return self.factory()
        return self._default

    @property
    def required(self) -> bool:
        """Indicates if this field is required for serialization.

        :type: bool
        """
        return self.const is UNDEFINED and self.default is UNDEFINED

    def _size_for_value(self, value: T) -> Optional[int]:  # noqa: ARG002
        """Get the size of the serialized value, or ``None`` if it can't be computed.

        This is an ugly hack for computing ``size`` properly when only ``const`` is
        given. It's *HIGHLY DISCOURAGED* to implement this function in your own field
        subclasses, since it *must not* call :meth:`from_stream`, :meth:`from_bytes`,
        :meth:`to_stream`, or :meth:`to_bytes`. Doing so could result in infinite
        recursion.

        :param value:
            The value to serialize.

        :return:
            The size of ``value`` when serialized, in bytes. If the size cannot be
            computed, return ``None``.
        :rtype: int
        """
        # Since this is called in the constructor we need to check to see if _size has
        # been assigned to yet.
        if self.has_fixed_size and hasattr(self, "_size"):
            return typing.cast(int, self._size)
        return None

    def _get_expected_size(self, field_values: StrDict) -> int:  # pragma: no cover
        """Compatibility shim -- this function was made public in 0.9.0."""
        warnings.warn(
            "_get_expected_size was made public in 0.9.0. The private form has been"
            " deprecated and will be removed in 1.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.get_expected_size(field_values)

    def get_expected_size(self, field_values: StrDict) -> int:
        """Determine the size of this field in bytes, given values for other fields.

        :param dict field_values:
            A dict mapping field names to their resolved values.

        :return:
            The number of bytes this field is expected to occupy.
        :rtype: int

        :raise MissingRequiredValueError:
            The field's size references another field but the other field is missing
            from ``field_values``.
        :raise UndefinedSizeError:
            The field doesn't have a defined size nor refers to another field to
            determine its size.

        .. versionchanged:: 0.9.0
            This used to be a private method. ``_get_expected_size()`` is still present
            for compatibility, but it will eventually be removed.
        """
        if isinstance(self.size, int):
            return self.size

        if self.size is None:
            # Field has an undefined size. If the caller gave us a value for that field,
            # or if we have a default value defined, we might be able to determine the
            # size of that value.
            return self.__get_expected_possibly_undefined_size(field_values)

        name = self.size.name if isinstance(self.size, Field) else self.size

        if name in field_values:
            expected_size = field_values[name]
            if not isinstance(expected_size, int):
                raise TypeError(
                    f"Field {self.name!r} relies on field {name!r} to give its size,"
                    f" but {name!r} has a non-integer value: {expected_size!r}"
                )
            return expected_size

        raise errors.MissingRequiredValueError(field=name)

    def __get_expected_possibly_undefined_size(self, field_values: StrDict) -> int:
        """Return the expected size of this field IF this field has no fixed size.

        .. warning::

            Do not call this if ``self.size`` is *not* null.
        """
        if self.name in field_values:
            # The value for the field is already set.
            value = field_values[self.name]
        elif self.default is not UNDEFINED:
            # Else: The value for this field isn't set, fall back to the default.
            value = self.default
        else:
            raise errors.UndefinedSizeError(field=self)

        try:
            if value is None:
                return len(self._get_null_repr(field_values))

            # If we get here then we have a value to get the size of. If that size can't
            # be determined (_size_for_value() returns None), we need to crash.
            size = self._size_for_value(value)
        except RecursionError:
            raise errors.BuggyFieldImplementationError(
                f"The implementation of {type(self).__module__}."
                f"{type(self).__qualname__} is broken: either _size_for_value() (or"
                " less likely, _get_null_repr()) calls one of the `Field.to_*` or"
                " `Field.from_*` methods. Doing so causes infinite recursion. (Value:"
                " {value!r})",
                field=self,
            ) from None

        if size is None:
            raise errors.UndefinedSizeError(field=self)
        return size

    def from_stream(  # noqa: C901
        self,
        stream: BinaryIO,
        context: object = None,
        loaded_fields: Optional[StrDict] = None,
    ) -> Union[T, None, _NotPresent]:
        """Load data from the given stream.

        :param BinaryIO stream:
            The stream to load data from.
        :param context:
            Additional data to pass to this method. Subclasses must ignore anything they
            don't recognize.
        :param dict loaded_fields:
            A dictionary of the fields that have already been loaded. This is set
            automatically when a field is loaded by a
            :class:`~binobj.structures.Struct`.

        :return: The deserialized data, or :data:`NOT_PRESENT`
        """
        if loaded_fields is None:
            loaded_fields = {}

        if not self.present(loaded_fields, context, stream):
            return self.not_present_value

        # If the caller passed in `null_value` as a byte string we'll peek ahead in the
        # stream and see if the bytes match up.
        if self.allow_null:
            try:
                null_repr = self._get_null_repr(loaded_fields)
            except errors.UnserializableValueError:
                # Null can't be represented in this current state, so we can't check to
                # see if the *raw binary* form is null. This isn't an error UNLESS
                # null_value is `DEFAULT`. If null_value is DEFAULT and we can't
                # determine the size, then we're out of luck.
                if self.null_value is DEFAULT:
                    raise errors.CannotDetermineNullError(field=self) from None
            else:
                potential_null_bytes = helpers.peek_bytes(stream, len(null_repr))
                if potential_null_bytes == null_repr:
                    # If we get here then the bytes we read ahead match null_value. Move
                    # the stream pointer to the beginning of the next field.
                    stream.seek(len(null_repr), os.SEEK_CUR)
                    for validator in self.validators:
                        validator(None)
                    return None

            # else: the bytes we read didn't match null_value. Fall through and try to
            # load the value using the field's normal loading code.

        # TODO (dargueta): This try-catch just to set the field feels dumb.
        try:
            loaded_value = self._do_load(
                stream, context=context, loaded_fields=loaded_fields
            )
        except errors.DeserializationError as err:
            err.field = self
            raise

        # Here we handle the case where null_value is DEFAULT or an instance of `T`
        # rather than a byte string. Note that there's no way for us to determine upon
        # loading if something matches DEFAULT. This is why we're deprecating setting
        # `null_value` to DEFAULT.
        if self.allow_null and loaded_value == self.null_value:
            loaded_value = None

        # TODO (dargueta): Change this to a validator instead.
        if self.const is not UNDEFINED and loaded_value != self.const:
            raise errors.ValidationError(field=self, value=loaded_value)

        for validator in self.validators:
            validator(loaded_value)

        return loaded_value

    def from_bytes(
        self,
        data: bytes,
        context: object = None,
        exact: bool = True,
        loaded_fields: Optional[StrDict] = None,
    ) -> Union[T, None, _NotPresent]:
        """Load from the given byte string.

        :param bytes data:
            A bytes-like object to get the data from.
        :param context:
            Additional data to pass to this method. Subclasses must ignore anything they
            don't recognize.
        :param bool exact:
            ``data`` must contain exactly the number of bytes required. If not all the
            bytes in ``data`` were used when reading the struct, throw an exception.
        :param dict loaded_fields:
            A dictionary of the fields that have already been loaded. This is set
            automatically when a field is loaded by a
            :class:`~binobj.structures.Struct`.

        :return: The deserialized data, or :data:`NOT_PRESENT` if the field is missing.
        """
        if loaded_fields is None:
            loaded_fields = {}

        stream = io.BytesIO(data)
        loaded_data = self.from_stream(stream, context, loaded_fields)

        here = stream.tell()
        stream.seek(0, os.SEEK_END)
        bytes_remaining = stream.tell() - here
        if exact and bytes_remaining > 0:
            raise errors.ExtraneousDataError(
                f"The input has {bytes_remaining} extra byte(s)."
            )
        return loaded_data

    @abc.abstractmethod
    def _do_load(
        self, stream: BinaryIO, context: object, loaded_fields: StrDict
    ) -> Optional[T]:
        """Load an object from the stream.

        :param BinaryIO stream:
        :param context:
            Additional data to pass to this method. Subclasses must ignore anything they
            don't recognize.
        :param dict loaded_fields:
            A dictionary of the fields that have already been loaded. This is guaranteed
            to not be ``None``.

        :return: The loaded object.
        """
        raise NotImplementedError

    def to_stream(  # noqa: C901
        self,
        stream: BinaryIO,
        data: Union[T, None, _Default] = DEFAULT,
        context: object = None,
        all_fields: Optional[StrDict] = None,
    ) -> None:
        """Convert the given data into bytes and write it to ``stream``.

        :param BinaryIO stream:
            The stream to write the serialized data into.
        :param data:
            The data to dump. Can be omitted only if this is a constant field or if a
            default value is defined.
        :param context:
            Additional data to pass to this method. Subclasses must ignore anything they
            don't recognize.
        :param dict all_fields:
            A dictionary of the fields about to be dumped. This is automatically set by
            the field's containing :class:`~binobj.structures.Struct`.
        """
        if all_fields is None:
            all_fields = {}

        if data is DEFAULT:
            # Typecast is not entirely truthful; this may return UNDEFINED if the field
            # has no default value.
            data = typing.cast(Optional[T], self.default)

        if data is UNDEFINED or data is DEFAULT:
            raise errors.MissingRequiredValueError(field=self)

        for validator in self.validators:
            validator(data)

        if data is None:
            stream.write(self._get_null_repr(all_fields))
            return

        buf = io.BytesIO()
        self._do_dump(buf, data, context=context, all_fields=all_fields)

        serialized_value = buf.getvalue()
        current_size = len(serialized_value)
        if self.has_fixed_size:
            expected_size = typing.cast(int, self.size)
        elif self.size is None:
            expected_size = current_size
        else:
            expected_size = self.get_expected_size(all_fields)

        size_diff = len(serialized_value) - expected_size

        if size_diff > 0:
            # Value is too long.
            raise errors.ValueSizeError(field=self, value=serialized_value)
        if size_diff < 0:
            serialized_value = self._add_padding(serialized_value, expected_size)

        stream.write(serialized_value)

    def _add_padding(self, serialized: bytes, to_size: int) -> bytes:  # noqa: ARG002
        """Given a serialized value, pad it out with bytes to the exact given length.

        :param bytes serialized: The serialized value.
        :param int to_size: The number of bytes to pad the serialized value out to.
        :return:
            The padded equivalent of `serialized`. Its length must be exactly `to_size`.

        .. note::

            This method is intended to be overridden. The default behavior is to crash.
        """
        raise errors.ValueSizeError(field=self, value=serialized)

    def to_bytes(
        self,
        data: Union[Optional[T], _Default] = DEFAULT,
        context: object = None,
        all_fields: Optional[StrDict] = None,
    ) -> bytes:
        """Convert the given data into bytes.

        :param data:
            The data to dump. Can be omitted only if this is a constant field or a
            default value is defined.
        :param context:
            Additional data to pass to this method. Subclasses must ignore anything they
            don't recognize.
        :param dict all_fields:
            A dictionary of the fields about to be dumped. This is automatically set by
            the field's containing :class:`~binobj.structures.Struct`.

        :return: The serialized data.
        :rtype: bytes
        """
        stream = io.BytesIO()
        self.to_stream(stream, data, context=context, all_fields=all_fields)
        return stream.getvalue()

    @abc.abstractmethod
    def _do_dump(
        self, stream: BinaryIO, data: T, context: object, all_fields: StrDict
    ) -> None:
        """Write the given data to the byte stream.

        :param BinaryIO stream:
            The stream to write to.
        :param data:
            The data to dump. Guaranteed to not be ``None``.
        :param context:
            Additional data to pass to this method. Subclasses must ignore anything they
            don't recognize.
        :param dict all_fields:
            A dictionary of the fields about to be dumped. This is guaranteed to not be
            ``None``.
        """
        raise errors.UnserializableValueError(field=self, value=data)

    def _get_null_repr(self, all_fields: Optional[StrDict] = None) -> bytes:
        """Return the serialized value for ``None``.

        We need this function because there's some logic involved in determining if
        ``None`` is a legal value, and guessing the serialization if no default value is
        provided.

        :return: The serialized form of ``None`` for this field.
        :rtype: bytes

        .. fixme::
            If null_value is given and this function is called inside _size_for_value()
            for a field, it will result in infinite recursion because of the call to
            :meth:`Field.to_bytes` here.
        """
        if all_fields is None:
            all_fields = {}

        if self.null_value is UNDEFINED:
            raise errors.UnserializableValueError(
                reason=f"`None` is not an acceptable value for {self}.",
                field=self,
                value=None,
            )
        if self.null_value not in (DEFAULT, None):
            if isinstance(self.null_value, bytes):
                return self.null_value

            # This is a bit of a hack. We can't call to_bytes() directly because that'll
            # trigger infinite recursion if we do. Thus, we have to call the dumping
            # function directly in all its ugly glory.
            buf = io.BytesIO()

            # Note: We need the typecast here because MyPy doesn't correctly detect that
            # we're filtering out DEFAULT in the `if` statement above. It thinks that
            # null_value can still be DEFAULT, so we cast it to this field's type.
            self._do_dump(
                buf,
                typing.cast(T, self.null_value),
                context=None,
                all_fields=all_fields,
            )
            return buf.getvalue()

        # User wants us to use all null bytes for the default null value.
        try:
            return b"\0" * self.get_expected_size(all_fields)
        except errors.UndefinedSizeError:
            raise errors.UnserializableValueError(
                reason=f"Can't guess appropriate serialization of `None` for {self}"
                " because it has no fixed size.",
                field=self,
                value=None,
            ) from None

    def _read_exact_size(
        self, stream: BinaryIO, loaded_fields: Optional[StrDict] = None
    ) -> bytes:
        """Read exactly the number of bytes this object takes up or crash.

        :param BinaryIO stream: The stream to read from.
        :param dict loaded_fields:
            A dict mapping names of fields to their loaded values. This allows us to
            read a variable-length field that depends on the value of another field
            occurring before it.


        :return: The correct number of bytes are read from the stream.
        :rtype: bytes

        :raise UnexpectedEOFError: Not enough bytes were left in the stream.

        .. versionchanged:: 0.6.1
            * Variable-length fields are now supported.
            * The ``loaded_fields`` argument.
        """
        if loaded_fields is None:
            loaded_fields = {}

        offset = stream.tell()
        n_bytes = self.get_expected_size(loaded_fields)

        data_read = stream.read(n_bytes)
        if len(data_read) < n_bytes:
            raise errors.UnexpectedEOFError(field=self, size=n_bytes, offset=offset)

        return data_read

    @overload
    def __get__(
        self, instance: None, owner: type[Struct]
    ) -> Field[T]: ...  # pragma: no cover

    @overload
    def __get__(
        self, instance: Struct, owner: type[Struct]
    ) -> Optional[T]: ...  # pragma: no cover

    # This annotation is bogus and only here to make MyPy happy. See bug report here:
    # https://github.com/python/mypy/issues/9416
    @overload
    def __get__(
        self, instance: Field[Any], owner: type[Field[Any]]
    ) -> Field[T]: ...  # pragma: no cover

    def __get__(self, instance, owner):  # type: ignore[no-untyped-def]
        if instance is None:
            return self
        if self.name in instance.__values__:
            return instance.__values__[self.name]
        return self.compute_value_for_dump(instance)

    def __set__(self, instance: Struct, value: Optional[T]) -> None:
        if self._compute_fn or self.const is not UNDEFINED:
            raise errors.ImmutableFieldError(field=self)

        for validator in self.validators:
            validator(value)
        instance.__values__[self.name] = value

    def __set_name__(self, owner: Struct, name: str) -> None:
        maybe_assign_name(self, name)

    def __str__(self) -> str:
        return f"{type(self).__qualname__}(name={self.name!r})"

    def __repr__(self) -> str:
        return f"<{self.__module__}.{self}>"


def maybe_assign_name(field: Field[Any], new_name: str) -> None:
    existing_name = getattr(field, "name", None)
    if existing_name is None:
        field.name = new_name
    elif new_name != existing_name:
        # The `name` attribute has already been set by __set_name__ and an explicit
        # name was passed into the constructor that doesn't match the existing name.
        raise errors.ConfigurationError(
            f"A name has already been set for this field ({existing_name!r}) but an"
            f" explicit name was also passed to the constructor ({new_name!r}).",
            field=field,
        )
