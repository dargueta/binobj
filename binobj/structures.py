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


# TODO (dargueta): Implement unions and bitfields.
