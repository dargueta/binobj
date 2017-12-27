"""Classes defining structures and unions."""

from binobj import serialization


class Struct(serialization.SerializableContainer):  # pylint: disable=too-few-public-methods
    """An ordered collection of fields and other structures."""
    def __str__(self):
        return type(self).__name__

    def get_field(self, stream, name, context=None):
        """Return the value of a single field.

        .. note ::
            If the field isn't at a fixed offset from the beginning of the
            struct (e.g. a variable-length field occurs before it) then the
            entire struct up to and including this field must be read.
            Unfortunately, this means that unrelated validation errors can be
            thrown if other fields are invalid.

        :param io.BytesIO stream:
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
        if name not in self.__components__:
            raise ValueError("%s doesn't have a field named %r." % (self, name))

        field = self.__components__[name]
        original_offset = stream.tell()

        # If the field is at a fixed offset from the beginning of the struct,
        # then we can read and return it directly.
        if field.offset is not None:
            try:
                stream.seek(original_offset + field.offset)
                return field.load(stream, context)
            finally:
                stream.seek(original_offset)

        # If we get here then the field is *not* at a fixed offset from the
        # beginning of the struct and we have to read everything up to it. This
        # can unfortunately result in validation errors if there is data before
        # the desired field that's invalid.
        try:
            loaded_data = self.partial_load(stream, name, context)
        finally:
            stream.seek(original_offset)
        return loaded_data[name]


class Array(serialization.Serializable):
    """An array of other serializable objects."""
    def __init__(self, component, *, count=None, halt_check=None, **kwargs):
        self.component = component
        self.count = count
        self.halt_check = halt_check or self._should_halt
        super().__init__(**kwargs)

    @staticmethod
    def _should_halt(seq, stream, loaded, context):    # pylint: disable=unused-argument
        """Determine if the deserializer should stop reading from the input.

        The default implementation does the following:

        - If the object has an integer attribute called ``count``, it compares
          ``count`` against the length of ``loaded``. If ``len(loaded)`` is less
          than ``count`` it'll return ``True`` (halt), ``False`` otherwise.
        - If the object *doesn't* have an attribute called ``count``, or
          ``count`` isn't an integer, the function returns ``True`` if there's
          any data left in the stream.

        :param SerializableSequence seq:
            The sequence being checked.
        :param io.BytesIO stream:
            The data stream to read from. Except in rare circumstances, this is
            the same stream that was passed to :meth:`load`. The stream pointer
            should be returned to its original position when the function exits.
        :param list loaded:
            A list of the objects that have been deserialized so far. In general
            this function *should not* modify the list. A possible exception to
            this rule is to remove a sentinel value from the end of the list.
        :param context:
            The ``context`` object passed to :meth:`load`.

        :return: ``True`` if the deserializer should stop reading, ``False``
            otherwise.
        :rtype: bool
        """
        if isinstance(seq.count, int):
            return seq.count <= len(loaded)

        offset = stream.tell()
        try:
            return stream.read(1) == b''
        finally:
            stream.seek(offset)

    def _do_dump(self, stream, data, context):
        """Convert the given data into bytes and write it to ``stream``.

        :param io.BytesIO stream:
            A binary stream to write the serialized data into.
        :param list data:
            The data to dump.
        :param context:
            Additional data to pass to this method. Subclasses must ignore
            anything they don't recognize.
        """
        for value in data:
            self.component.dump(stream, value, context)

    def _do_load(self, stream, context=None):
        """Load a structure list from the given stream.

        :param io.BytesIO stream:
            A bit stream to read data from.
        :param context:
            Additional data to pass to this method. Subclasses must ignore
            anything they don't recognize.

        :return: The deserialized data.
        :rtype: list
        """
        result = []
        while not self.halt_check(self, stream, result, context):
            result.append(self.component.load(stream, context))

        return result


# TODO (dargueta): Implement unions and bitfields.
