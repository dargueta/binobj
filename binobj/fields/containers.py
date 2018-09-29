"""Fields used for forming more complex structures with other fields."""


from binobj import errors
from binobj.fields.base import Field


class Array(Field):
    """An array of other serializable objects.

    :param Field component:
        The component this array is comprised of.
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
    """
    def __init__(self, component, *, count=None, halt_check=None, **kwargs):
        super().__init__(**kwargs)
        self.component = component
        self.halt_check = halt_check or self.should_halt

        if count is None or (isinstance(count, (int, str, Field))
                             and not isinstance(count, bool)):
            # The isinstance bool check is needed because `bool` is a subclass
            # of `int`.
            self.count = count
        else:
            raise TypeError('`count` must be an integer, string, or a `Field`.')

    @staticmethod
    def should_halt(seq, stream, values, context, loaded_fields):    # pylint: disable=unused-argument
        """Determine if the deserializer should stop reading from the input.

        The default implementation does the following:

        - If the ``Array`` has an integer ``count``, it compares ``count``
          against the length of ``values``. If ``len(values)`` is equal to or
          more than ``count`` it'll return ``True`` (halt), ``False`` otherwise.
        - If the object *doesn't* have an attribute called ``count``, or
          ``count`` isn't an integer, the function returns ``True`` if there's
          any data left in the stream.

        :param Array seq:
            The sequence being checked.
        :param io.BufferedIOBase stream:
            The data stream to read from. Except in rare circumstances, this is
            the same stream that was passed to :meth:`load`. The stream pointer
            should be returned to its original position when the function exits.
        :param list values:
            A list of the objects that have been deserialized so far. In general
            this function *should not* modify the list. A possible exception to
            this rule is to remove a sentinel value from the end of the list.
        :param context:
            The ``context`` object passed to :meth:`load`.
        :param dict loaded_fields:
            The fields in the struct that have been loaded so far.

        :return: ``True`` if the deserializer should stop reading, ``False``
            otherwise.
        :rtype: bool
        """
        if isinstance(seq.count, int):
            return seq.count <= len(values)
        if isinstance(seq.count, Field):
            return loaded_fields[seq.count.name] <= len(values)
        if isinstance(seq.count, str):
            # The number of fields in this array is a field that should already
            # have been loaded.
            if seq.count not in loaded_fields:
                # Instead of throwing a KeyError, we'll throw a more helpful
                # exception.
                raise errors.FieldReferenceError(
                    "%r is either not a field in this struct or hasn't been "
                    "loaded yet." % seq.count, field=seq.count)
            return loaded_fields[seq.count] <= len(values)

        # Else: count is None. Our only option is to check to see if we hit EOF.

        offset = stream.tell()
        try:
            return stream.read(1) == b''
        finally:
            stream.seek(offset)

    def _do_dump(self, stream, data, context, all_fields):
        """Convert the given data into bytes and write it to ``stream``.

        :param io.BufferedIOBase stream:
            A binary stream to write the serialized data into.
        :param list data:
            The data to dump.
        :param context:
            Additional data to pass to this method. Subclasses must ignore
            anything they don't recognize.
        :param dict all_fields:
            A dictionary of the fields about to be dumped. This is guaranteed to
            not be ``None``.
        """
        for value in data:
            self.component.dump(stream, value, context=context,
                                all_fields=all_fields)

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
        while not self.halt_check(self, stream, result, context=context,
                                  loaded_fields=loaded_fields):
            result.append(
                self.component.load(stream, context=context,
                                    loaded_fields=loaded_fields)
            )

        return result


class Nested(Field):
    """Used to nest one struct inside of another.

    :param Type[binobj.structures.Struct] struct_class:
        The struct class to wrap as a field. Not an instance!
    """
    def __init__(self, struct_class, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.struct_class = struct_class

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
        * ``context``: Additional data to pass directly to the loader selected
          from ``classes``.
        * ``loaded_fields``: A dictionary of the fields that have already been
          loaded. This is guaranteed to not be ``None``.

    :param callable dump_decider:
        A function that decides which :class:`~binobj.structures.Struct` class or
        :class:`~binobj.fields.base.Field` instance to use for dumping the given
        data. It must take four arguments:

        * ``data``: A dictionary containing the data to dump.
        * ``classes``: A list of classes that can be used for dumping.
        * ``context``: Additional data to pass directly to the dumper selected
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
                'You must pass an instance of a Field, not a class.', field=self)

        self.choices = choices
        self.load_decider = load_decider
        self.dump_decider = dump_decider

    def _do_dump(self, stream, data, context, all_fields):
        dumper = self.dump_decider(data, self.choices, context, all_fields)
        if isinstance(dumper, Field):
            return dumper.dump(stream, data, context, all_fields)

        # Else: Dumper is not a Field instance, assume this is a Struct.
        return dumper(**data).to_stream(stream, context)

    def _do_load(self, stream, context, loaded_fields):
        loader = self.load_decider(stream, self.choices, context, loaded_fields)
        if isinstance(loader, Field):
            return loader.load(stream, context, loaded_fields)

        # Else: loader is not a Field instance, assume this is a Struct.
        return loader.from_stream(stream, context)
