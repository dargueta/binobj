"""Fields used for forming more complex structures with other fields."""

import collections.abc

from binobj import errors
from binobj.fields.base import Field


__all__ = ["Array", "Nested", "Union"]


class Array(Field):
    """An array of other serializable objects.

    :param Field component:
        The component this array is comprised of. Must be an instance.
    :param count:
        Optional. Some way of indicating the number of elements in this array.
        The value for this argument can be one of the following:

        * An integer. The array always contains this many elements.
        * A :class:`~binobj.fields.base.Field` instance that must 1) be an
          integer; 2) occur before this array in the same struct.
        * A string naming a field fitting the above criteria. You'll need this
          if your size field's name is a Python keyword.

        .. versionchanged:: 0.3.0
            ``count`` can now be a :class:`~binobj.fields.base.Field` or string.

    :param callable halt_check:
        A function taking five arguments. See :meth:`should_halt` for the
        default implementation. Subclasses can override this function if desired
        to avoid having to pass in a custom function every time.

    .. versionchanged:: 0.6.1
        :meth:`.to_stream` and :meth:`.to_bytes` throw an :class:`~.errors.ArraySizeError`
        if ``count`` is set and the iterable passed in is too long. Due to a bug
        it used to be ignored when dumping.

    .. versionchanged:: 0.7.0
        :attr:`.size` is set if ``component.size`` is defined and ``count`` is
        an integer constant.
    """

    def __init__(self, component, *, count=None, halt_check=None, **kwargs):
        super().__init__(**kwargs)
        self.component = component
        self.halt_check = halt_check or self.should_halt

        if count is None or (
            isinstance(count, (int, str, Field)) and not isinstance(count, bool)
        ):
            # The isinstance bool check is needed because `bool` is a subclass
            # of `int`.
            self.count = count
        else:
            raise TypeError("`count` must be an integer, string, or a `Field`.")

        if isinstance(self.count, int) and component.size is not None:
            self._size = self.count * component.size

    def get_final_element_count(self, field_values):
        """Calculate the number of elements in the array based on other fields' values.

        :param dict field_values:
            A dict mapping field names to their deserialized values. It doesn't
            need to have every value in the struct; if ``count`` references a
            field, it only requires that field to be present.

        :return:
            The expected number of elements in this array, or ``None`` if the
            array doesn't have a fixed size.
        :rtype: int

        .. versionadded:: 0.6.1
        """
        if self.count is None:
            return None
        if isinstance(self.count, int):
            return self.count

        if isinstance(self.count, Field):
            name = self.count.name
        elif isinstance(self.count, str):
            name = self.count
        else:
            raise TypeError(
                "Unexpected type for `count`: %r" % type(self.count).__name__
            )

        # The number of fields in this array is a field that should already have
        # been loaded.
        if name not in field_values:
            raise errors.FieldReferenceError(
                "Array size depends on field %r but it wasn't found." % name,
                field=self.count,
            )
        return field_values[name]

    @staticmethod
    def should_halt(seq, stream, values, context, loaded_fields):
        """Determine if the deserializer should stop reading from the input.

        This function should return ``True`` to indicate loading for this field
        should stop, or ``False`` to continue adding elements.

        The default implementation does the following:

        - If ``count`` is an integer, it compares ``count`` against the length
          of ``values``. If ``len(values)`` is equal to or more than ``count``
          it'll return ``True`` (halt), ``False`` otherwise.
        - If ``count`` is a :class:`~binobj.fields.base.Field`, that field should
          already have been loaded and in ``loaded_fields``. The expected array
          size is taken from there, and compared as above.
        - If ``count`` is a string, it's the name of a field already loaded and
          in ``loaded_fields``. The expected array size is taken from there, and
          compared as above.
        - Otherwise, the function assumes the array ends at EOF and only returns
          ``True`` if there's no more data in the stream.

        Subclasses' implementations must handle all four cases.

        :param Array seq:
            The sequence being checked.
        :param io.BufferedIOBase stream:
            The data stream to read from. Except in rare circumstances, this is
            the same stream that was passed to :meth:`.from_stream`. The stream
            pointer should be returned to its original position when the function
            exits.
        :param list values:
            A list of the objects that have been deserialized so far. In general
            this function *should not* modify the list. A possible exception to
            this rule is to remove a sentinel value from the end of the list.
        :param context:
            The ``context`` object passed to :meth:`.from_stream`.
        :param dict loaded_fields:
            The fields in the struct that have been loaded so far.

        :return: ``True`` if the deserializer should stop reading, ``False``
            otherwise.
        :rtype: bool
        """
        if seq.count is not None:
            return seq.get_final_element_count(loaded_fields) <= len(values)

        # Else: count is None. Our only option is to check to see if we hit EOF.
        offset = stream.tell()
        try:
            return stream.read(1) == b""
        finally:
            stream.seek(offset)

    def _do_dump(self, stream, data, context, all_fields):
        """Convert the given data into bytes and write it to ``stream``.

        :param io.BufferedIOBase stream:
            A binary stream to write the serialized data into.
        :param iterable data:
            An iterable of values to dump.
        :param context:
            Additional data to pass to this method. Subclasses must ignore
            anything they don't recognize.
        :param dict all_fields:
            A dictionary of the fields about to be dumped. This is guaranteed to
            not be ``None``.
        """
        n_elems = self.get_final_element_count(all_fields)
        if not isinstance(data, collections.abc.Sized):
            self._dump_unsized(stream, data, n_elems, context, all_fields)
            return

        if n_elems is not None and len(data) != n_elems:
            raise errors.ArraySizeError(
                field=self, n_expected=n_elems, n_given=len(data)
            )

        for value in iter(data):
            self.component.to_stream(stream, value, context, all_fields)

    def _dump_unsized(self, stream, data, n_elems, context, all_fields):
        """Dump an unsized iterable into the stream."""
        n_written = 0
        for value in data:
            if n_written == n_elems:
                # We've already written the requisite number of items to the
                # stream, but received at least one more item. Crash.
                raise errors.ArraySizeError(
                    field=self, n_expected=n_elems, n_given=n_written + 1
                )

            self.component.to_stream(
                stream, value, context=context, all_fields=all_fields
            )
            n_written += 1

        if n_written < n_elems:
            raise errors.ArraySizeError(
                field=self, n_expected=n_elems, n_given=n_written
            )

    def _do_load(self, stream, context, loaded_fields):
        """Load a structure list from the given stream.

        :param io.BufferedIOBase stream:
            A bit stream to read data from.
        :param context:
            Additional data to pass to this method. Subclasses must ignore
            anything they don't recognize.
        :param dict loaded_fields:
            A dictionary of the fields that have already been loaded. This is
            guaranteed to not be ``None``.

        :return: The deserialized data.
        :rtype: list
        """
        result = []
        while not self.halt_check(
            self, stream, result, context=context, loaded_fields=loaded_fields
        ):
            component = self.component.from_stream(stream, context, loaded_fields)
            result.append(component)

        return result


class Nested(Field):
    """Used to nest one struct inside of another.

    :param Type[~binobj.structures.Struct] struct_class:
        The struct class to wrap as a field. Not an instance!

    .. code-block:: python

        class Address(Struct):
            ...

        class Person(Struct):
            name = fields.StringZ()
            address = fields.Nested(Address)

    .. versionchanged:: 0.7.0
        :attr:`.size` is set if the struct passed in is of fixed size. Prior to
        0.7.0, ``Person.get_size()`` would be None even if ``Address.get_size()``
        returned a value. Now the sizes are the same.
    """

    def __init__(self, struct_class, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.struct_class = struct_class
        self._size = struct_class.get_size()

    def _do_dump(self, stream, data, context, all_fields):
        instance = self.struct_class(**data)
        return instance.to_stream(stream, context)

    def _do_load(self, stream, context, loaded_fields):
        return self.struct_class.from_stream(stream, context)


class Union(Field):
    """A field that can be one of several different types of structs or fields.

    :param choices:
        One or more :class:`~binobj.structures.Struct` classes or
        :class:`~binobj.fields.base.Field` instances that can be used for
        loading and dumping.

    :param callable load_decider:
        A function that decides which :class:`~binobj.structures.Struct` class or
        :class:`~binobj.fields.base.Field` instance to use for loading the input.
        It must take four arguments:

        * ``stream``: The stream being loaded from.
        * ``classes``: A list of classes that can be used for loading.
        * ``context``: The context object to pass directly to the loader selected
          from ``classes``.
        * ``loaded_fields``: A dictionary of the fields that have already been
          loaded. This is guaranteed to not be ``None``.

    :param callable dump_decider:
        A function that decides which :class:`~binobj.structures.Struct` class or
        :class:`~binobj.fields.base.Field` instance to use for dumping the given
        data. It must take four arguments:

        * ``data``: The data to dump. This can be any type.
        * ``classes``: A list of classes that can be used for dumping.
        * ``context``: The context object to pass directly to the dumper selected
          from ``classes``.
        * ``all_fields``: A dictionary of the fields about to be dumped. This is
          guaranteed to not be ``None``.

    .. versionadded:: 0.3.0

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
    """

    def __init__(self, *choices, load_decider, dump_decider, **kwargs):
        super().__init__(**kwargs)
        if any(isinstance(c, type) and issubclass(c, Field) for c in choices):
            raise errors.ConfigurationError(
                "You must pass an instance of a Field, not a class.", field=self
            )

        self.choices = choices
        self.load_decider = load_decider
        self.dump_decider = dump_decider

    def _do_dump(self, stream, data, context, all_fields):
        dumper = self.dump_decider(data, self.choices, context, all_fields)
        if isinstance(dumper, Field):
            return dumper.to_stream(stream, data, context, all_fields)

        # Else: Dumper is not a Field instance, assume this is a Struct.
        return dumper(**data).to_stream(stream, context)

    def _do_load(self, stream, context, loaded_fields):
        loader = self.load_decider(stream, self.choices, context, loaded_fields)
        if isinstance(loader, Field):
            return loader.from_stream(stream, context, loaded_fields)

        # Else: loader is not a Field instance, assume this is a Struct.
        return loader.from_stream(stream, context)
