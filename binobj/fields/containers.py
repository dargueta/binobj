"""Fields used for forming more complex structures with other fields."""

from __future__ import annotations

import typing
from collections.abc import Iterable
from collections.abc import Mapping
from collections.abc import MutableSequence
from collections.abc import Sequence
from collections.abc import Sized
from typing import Any
from typing import BinaryIO
from typing import Callable
from typing import Optional
from typing import overload
from typing import TypeVar
from typing import Union as _Union

from typing_extensions import override
from typing_extensions import TypeAlias

from binobj import errors
from binobj.fields.base import Field
from binobj.fields.base import maybe_assign_name
from binobj.fields.base import NOT_PRESENT
from binobj.structures import Struct
from binobj.typedefs import StrDict


__all__ = ["Array", "Nested", "Union"]


T = TypeVar("T")
TStruct = TypeVar("TStruct", bound=Struct)


HaltCheckFn: TypeAlias = Callable[
    ["Array[T]", BinaryIO, MutableSequence[Optional[T]], Any, StrDict], bool
]
"""A function used to detect the end of an array when deserializing.

See :meth:`Array.should_halt` for a full description of arguments.
"""


FieldLoadDecider: TypeAlias = Callable[
    [BinaryIO, Sequence[Field[Any]], Any, StrDict], Field[Any]
]

FieldDumpDecider: TypeAlias = Callable[
    [Any, Sequence[Field[Any]], Any, StrDict], Field[Any]
]

StructLoadDecider: TypeAlias = Callable[
    [BinaryIO, Sequence[type[Struct]], Any, StrDict], type[Struct]
]
StructDumpDecider: TypeAlias = Callable[
    [Any, Sequence[type[Struct]], Any, StrDict], type[Struct]
]


class Array(Field[list[Optional[T]]]):
    """An array of other serializable objects.

    :param Field component:
        The component this array is comprised of. Must be an instance.
    :param count:
        Optional. Some way of indicating the number of elements in this array. The value
        for this argument can be one of the following:

        * An integer. The array always contains this many elements.
        * A :class:`~binobj.fields.base.Field` instance that must 1) be an integer;
          2) occur before this array in the same struct.
        * A string naming a field fitting the above criteria. You'll need this if your
          size field's name is a Python keyword.

    :param callable halt_check:
        A function taking five arguments. See :meth:`should_halt` for the default
        implementation. Subclasses can override this function if desired to avoid having
        to pass in a custom function every time. For further details, see
        :data:`HaltCheckFn`.

    .. versionchanged:: 0.3.0
        ``count`` can now be a :class:`~.fields.base.Field` or string.

    .. versionchanged:: 0.6.1
        :meth:`~.fields.base.Field.to_stream` and :meth:`~.fields.base.Field.to_bytes`
        throw an :class:`~.errors.ArraySizeError` if ``count`` is set and the iterable
        passed in is too long. Due to a bug it used to be ignored when dumping.

    .. versionchanged:: 0.7.0
        :attr:`.size` is set if ``component.size`` is defined and ``count`` is an
        integer constant.
    """

    def __init__(
        self,
        component: Field[T],
        *,
        count: _Union[int, Field[int], str, None] = None,
        halt_check: Optional[HaltCheckFn[T]] = None,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.component = component
        self.halt_check = halt_check or self.should_halt
        maybe_assign_name(self.component, self.name)

        if count is None or (
            isinstance(count, (int, str, Field)) and not isinstance(count, bool)
        ):
            # The isinstance bool check is needed because `bool` is a subclass of `int`.
            self.count = count
        else:
            raise TypeError("`count` must be an integer, string, or a `Field`.")

        if isinstance(self.count, int) and component.has_fixed_size:
            self._size = self.count * typing.cast(int, component.size)

    def get_final_element_count(self, field_values: StrDict) -> Optional[int]:
        """Calculate the number of elements in the array based on other fields' values.

        :param dict field_values:
            A dict mapping field names to their deserialized values. It doesn't need to
            have every value in the struct; if :attr:`count` references a field, it only
            requires that field to be present here.

        :return:
            The expected number of elements in this array, or ``None`` if the array
            doesn't have a fixed size.
        :rtype: int

        .. versionadded:: 0.6.1
        .. versionchanged:: 0.8.0
            Throws a `ConfigurationError` if this field's :attr:`count` is a `Field` but
            doesn't have an assigned name.
        """
        if self.count is None:
            return None
        if isinstance(self.count, int):
            return self.count

        if isinstance(self.count, Field):
            name = self.count.name
            if name is None:
                # This will only happen if someone creates a field outside a Struct and
                # passes it to this field as the count object.
                raise errors.ConfigurationError(
                    f"`count` field for {self!r} has no assigned name.",
                    field=self.count,
                )
        elif isinstance(self.count, str):
            name = self.count
        else:
            # We check the type of `self.count` in the constructor so this should never
            # happen.
            raise TypeError(
                f"Unexpected type for `count`: {type(self.count).__qualname__!r}"
            )

        # The number of fields in this array is a field that should already have been
        # loaded.
        if name not in field_values:
            raise errors.FieldReferenceError(
                f"Array size depends on field {name!r} but it wasn't found.",
                field=name,
            )
        return typing.cast(int, field_values[name])

    @staticmethod
    def should_halt(
        seq: Array[T],
        stream: BinaryIO,
        values: list[Optional[T]],
        context: object,  # noqa: ARG004
        loaded_fields: StrDict,
    ) -> bool:
        """Determine if the deserializer should stop reading from the input.

        This function should return ``True`` to indicate loading for this field should
        stop, or ``False`` to continue adding elements.

        The default implementation does the following:

        - If ``count`` is an integer, it compares ``count`` against the length of
          ``values``. If ``len(values)`` is equal to or more than ``count`` it'll return
          ``True`` (halt), ``False`` otherwise.
        - If ``count`` is a :class:`~binobj.fields.base.Field`, that field should
          already have been loaded and in ``loaded_fields``. The expected array size is
          taken from there, and compared as above.
        - If ``count`` is a string, it's the name of a field already loaded and in
          ``loaded_fields``. The expected array size is taken from there, and compared
          as above.
        - Otherwise, the function assumes the array ends at EOF and only returns
          ``True`` if there's no more data in the stream.

        Subclasses' implementations must handle all four cases.

        :param Array seq:
            The sequence being checked.
        :param BinaryIO stream:
            The data stream to read from. Except in rare circumstances, this is the same
            stream that was passed to :meth:`~.fields.base.Field.from_stream`. The
            stream pointer should be returned to its original position when the function
            exits.
        :param list values:
            A list of the objects that have been deserialized so far. In general this
            function *should not* modify the list. A possible exception to this rule is
            to remove a sentinel value from the end of the list.
        :param context:
            The ``context`` object passed to :meth:`~.fields.base.Field.from_stream`.
        :param dict loaded_fields:
            The fields in the struct that have been loaded so far.

        :return: ``True`` if the deserializer should stop reading, ``False``
            otherwise.
        :rtype: bool

        .. versionchanged:: 0.8.0
            The default implementation now throws :class:`~.errors.UndefinedSizeError`
            if the length of the array couldn't be determined. Previously this would
            crash with a :class:`TypeError`.
        """
        if seq.count is not None:
            count = seq.get_final_element_count(loaded_fields)
            if count is None:  # pragma: no cover
                # Theoretically this should never happen, as get_final_element_count()
                # should only return None if seq.count is None.
                raise errors.UndefinedSizeError(field=seq)
            return count <= len(values)

        # Else: count is None. Our only option is to check to see if we hit EOF.
        offset = stream.tell()
        try:
            return stream.read(1) == b""
        finally:
            stream.seek(offset)

    def _do_dump(
        self,
        stream: BinaryIO,
        data: Iterable[Optional[T]],
        context: object,
        all_fields: StrDict,
    ) -> None:
        """Convert the given data into bytes and write it to ``stream``.

        :param BinaryIO stream:
            A binary stream to write the serialized data into.
        :param iterable data:
            An iterable of values to dump.
        :param context:
            Additional data to pass to this method. Subclasses must ignore anything they
            don't recognize.
        :param dict all_fields:
            A dictionary of the fields about to be dumped. This is guaranteed to not be
            ``None``.
        """
        n_elems = self.get_final_element_count(all_fields)
        if not isinstance(data, Sized):
            self._dump_unsized(stream, data, n_elems, context, all_fields)
            return

        if n_elems is not None and len(data) != n_elems:
            raise errors.ArraySizeError(
                field=self, n_expected=n_elems, n_given=len(data)
            )

        for value in iter(data):
            self.component.to_stream(stream, value, context, all_fields)

    def _dump_unsized(
        self,
        stream: BinaryIO,
        data: Iterable[Optional[T]],
        n_elems: Optional[int],
        context: object,
        all_fields: StrDict,
    ) -> None:
        """Dump an unsized iterable into the stream."""
        n_written = 0
        for value in data:
            if n_written == n_elems:
                # We've already written the requisite number of items to the stream, but
                # received at least one more item. Crash.
                raise errors.ArraySizeError(
                    field=self, n_expected=n_elems, n_given=n_written + 1
                )

            self.component.to_stream(
                stream, value, context=context, all_fields=all_fields
            )
            n_written += 1

        if n_elems is not None and n_written < n_elems:
            raise errors.ArraySizeError(
                field=self, n_expected=n_elems, n_given=n_written
            )

    def _do_load(
        self, stream: BinaryIO, context: object, loaded_fields: StrDict
    ) -> list[Optional[T]]:
        """Load a structure list from the given stream.

        :param BinaryIO stream:
            A bit stream to read data from.
        :param context:
            Additional data to pass to this method. Subclasses must ignore anything they
            don't recognize.
        :param dict loaded_fields:
            A dictionary of the fields that have already been loaded. This is guaranteed
            to not be ``None``.

        :return: The deserialized data.
        :rtype: list
        """
        result: list[Optional[T]] = []
        while not self.halt_check(self, stream, result, context, loaded_fields):
            component = self.component.from_stream(stream, context, loaded_fields)
            if component is NOT_PRESENT:
                continue
            result.append(component)

        return result


class Nested(Field[TStruct]):
    """Used to nest one struct inside of another.

    :param type[~binobj.structures.Struct] struct_class:
        The struct class to wrap as a field. Not an instance!

    .. code-block:: python

        class Address(Struct):
            ...Any

        class Person(Struct):
            name = fields.StringZ()
            address = fields.Nested(Address)

    .. versionchanged:: 0.7.0
        :attr:`.size` is set if the struct passed in is of fixed size. Prior to 0.7.0,
        ``Person.get_size()`` would be None even if ``Address.get_size()`` returned a
        value. Now the sizes are the same.
    """

    def __init__(self, struct_class: type[TStruct], *args: object, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.struct_class = struct_class
        self._size = struct_class.get_size()

    @override
    def _do_dump(
        self,
        stream: BinaryIO,
        data: _Union[StrDict, TStruct],
        context: object,
        all_fields: StrDict,
    ) -> None:
        if isinstance(data, Struct):
            data.to_stream(stream, context)
        else:
            instance = self.struct_class(**typing.cast(StrDict, data))
            instance.to_stream(stream, context)

    @override
    def _do_load(
        self, stream: BinaryIO, context: object, loaded_fields: StrDict
    ) -> TStruct:
        return self.struct_class.from_stream(stream, context)


class Union(Field[Any]):
    """A field that can be one of several different types of structs or fields.

    :param choices:
        One or more :class:`~binobj.structures.Struct` classes or
        :class:`~binobj.fields.base.Field` instances that can be used for loading and
        dumping.

    :param callable load_decider:
        A function that decides which :class:`~binobj.structures.Struct` class or
        :class:`~binobj.fields.base.Field` instance to use for loading the input. It
        must take four arguments:

        * ``stream``: The stream being loaded from.
        * ``classes``: A list of classes that can be used for loading.
        * ``context``: The context object to pass directly to the loader selected from
          ``classes``.
        * ``loaded_fields``: A dictionary of the fields that have already been loaded.
          This is guaranteed to not be ``None``.

    :param callable dump_decider:
        A function that decides which :class:`~binobj.structures.Struct` class or
        :class:`~binobj.fields.base.Field` instance to use for dumping the given data.
        It must take four arguments:

        * ``data``: The data to dump. This can be any type.
        * ``classes``: A list of classes that can be used for dumping.
        * ``context``: The context object to pass directly to the dumper selected from
          ``classes``.
        * ``all_fields``: A dictionary of the fields about to be dumped. This is
          guaranteed to not be ``None``.

    Usage with Structs::

        def load_decider(stream, classes, context, loaded_fields):
            data_type_id = loaded_fields['data_type']
            return classes[data_type_id]

        def dump_decider(data, classes, context, all_fields):
            data_type_id = all_fields['data_type']
            return classes[data_type_id]

        class MyStruct(Struct):
            data_type = UInt8()
            data = Union(UserInfo, FileInfo, SystemInfo,
                         load_decider=load_decider, dump_decider=dump_decider)

    Usage with Fields::

        class FieldsUnionContainer(binobj.Struct):
            data_type = fields.UInt8()
            item = fields.Union(fields.StringZ(),
                                fields.UInt16(endian='little'),
                                load_decider=fields_load_decider,
                                dump_decider=fields_dump_decider)

    .. versionadded:: 0.3.0
    """

    @overload
    def __init__(
        self,
        *choices: Field[Any],
        load_decider: FieldLoadDecider,
        dump_decider: FieldDumpDecider,
        **kwargs: Any,
    ):
        pass

    @overload
    def __init__(
        self,
        *choices: type[Struct],
        load_decider: StructLoadDecider,
        dump_decider: StructDumpDecider,
        **kwargs: Any,
    ):
        pass

    def __init__(
        self,
        *choices: Any,
        load_decider: Any,
        dump_decider: Any,
        **kwargs: Any,
    ):
        if any(isinstance(c, type) and issubclass(c, Field) for c in choices):
            raise errors.ConfigurationError(
                "A `Union` must be passed Field instances, not classes.", field=self
            )

        super().__init__(**kwargs)
        self.choices = choices
        self.load_decider = load_decider
        self.dump_decider = dump_decider

    @override
    def _do_dump(
        self, stream: BinaryIO, data: Any, context: object, all_fields: StrDict
    ) -> None:
        dumper = self.dump_decider(data, self.choices, context, all_fields)
        if isinstance(dumper, Field):
            dumper.to_stream(stream, data, context, all_fields)
        elif issubclass(dumper, Struct):
            if not isinstance(data, Mapping):
                raise TypeError(
                    f"Cannot dump a non-Mapping-like object as a {dumper!r}: {data!r}",
                )
            dumper(**data).to_stream(stream, context)
        else:
            raise TypeError(
                f"Dump decider returned a {type(dumper)}, expected a Field instance or"
                " subclass of Struct."
            )

    @override
    def _do_load(
        self, stream: BinaryIO, context: object, loaded_fields: StrDict
    ) -> Any:
        loader = self.load_decider(stream, self.choices, context, loaded_fields)
        if isinstance(loader, Field):
            return loader._do_load(stream, context, loaded_fields)  # noqa: SLF001
        if isinstance(loader, type) and issubclass(loader, Struct):
            return loader.from_stream(stream, context)
        raise TypeError(
            f"Load decider returned a {type(loader)!r}, expected a Field instance or"
            " subclass of Struct."
        )
