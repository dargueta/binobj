"""Errors for the binobj package."""


class Error(Exception):
    """Base class for all binobj errors.

    Do not throw this exception directly.
    """
    def __init__(self, message=None, *args):
        # If there is no error message, use the first line of the docstring.
        if message is None:
            message = self.__doc__.splitlines()[0]
        super().__init__(message, *args)


class ConfigurationError(Error):
    """A field or struct was misconfigured.

    :param str message: A description of what's wrong with the field.
    :param ~binobj.fields.Field field: The offending field.
    """
    def __init__(self, message=None, *, field):
        super().__init__(message)
        self.field = field


class SerializationError(Error):
    """An error occurred while serializing data.

    :param str message:
        An error message explaining the problem.
    :param ~binobj.structures.Struct struct:
        The struct that contains the field that failed to be serialized.
    :param ~binobj.fields.Field field:
        The field that failed to be serialized.
    :param value:
        The value that caused the crash.
    """
    def __init__(self, message=None, *, struct=None, field=None, value=None):
        super().__init__(message)
        self.struct = struct
        self.field = field
        self.value = value


class DeserializationError(Error):
    """An error occurred while deserializing data.

    :param str message:
        An error message explaining the problem.
    :param ~binobj.fields.Field field:
        The field that failed to load.
    :param bytes data:
        The raw data that was read that led to the crash.
    :param int offset:
        The offset into the data stream where the crash occurred.
    """
    def __init__(self, message=None, *, field=None, data=None, offset=None):
        super().__init__(message)
        self.field = field
        self.data = data
        self.offset = offset


class ValidationError(Error):
    """Validation failed for one or more fields.

    :param str message:
        An error message explaining the problem.
    :param ~binobj.fields.Field field:
        The field that failed validation.
    :param value:
        The invalid value.
    """
    def __init__(self, message=None, *, field, value):
        if not message:
            message = 'Invalid value for %s: %r' % (field, value)

        super().__init__(message)
        self.field = field
        self.value = value


class FieldReferenceError(Error):
    """An error occurred while computing a field reference."""


################################################################################


class UnserializableValueError(SerializationError):
    """The value couldn't be serialized."""
    def __init__(self, *, field, value, reason=None):
        if reason is not None:
            message = "%s can't serialize value: %s" % (field, reason)
        else:
            message = "%s can't serialize value of type %r." \
                      % (field, type(value).__name__)
        super().__init__(message, field=field, value=value)


class MissingRequiredValueError(SerializationError):
    """No value was passed for a required field.

    :param ~binobj.fields.Field field:
        The missing field, or its name.
    """
    def __init__(self, *, field):
        super().__init__('Missing required value for field: %s' % field,
                         field=field)


class UnexpectedValueError(SerializationError):
    """The data to dump has unexpected fields.

    :param ~binobj.structures.Struct struct:
        The struct performing the serialization.
    :param str name:
        Either a string or an iterable of strings, each being the name of a
        field that was unexpected. Don't pass :class:`~binobj.fields.Field`
        instances.
    """
    def __init__(self, *, struct, name):
        if isinstance(name, str):
            self.names = {name}
        else:
            self.names = set(name)

        msg = '%d unrecognized field(s) given to %s for serialization: %s' % (
            len(self.names), type(struct).__name__,
            ', '.join(repr(f) for f in sorted(self.names)))

        super().__init__(msg, struct=struct)


class ValueSizeError(UnserializableValueError):
    """The value can't be serialized because it doesn't fit into the field."""
    def __init__(self, *, field, value):
        super().__init__(reason="Value doesn't fit into %r bytes." % field.size,
                         field=field, value=value)


class VariableSizedFieldError(DeserializationError):
    """Expected a fixed-length field but the field is of a variable size."""
    def __init__(self, *, field, offset=None):
        msg = "Can't read fixed number of bytes from variable-length field: " \
            + str(field)
        super().__init__(msg, field=field, offset=offset)


class UnexpectedEOFError(DeserializationError):
    """Hit EOF while reading, but expected more data.

    :param ~binobj.fields.Field field:
        The field that failed to be deserialized.
    :param int size:
        The number of bytes that were attempted to be read.
    :param int offset:
        The offset into the input stream/string where the error was encountered,
        in bytes.
    """
    def __init__(self, *, field, size, offset):
        super().__init__(
            'Unexpected EOF while trying to read %d bytes at offset %d.'
            % (size, offset),
            field=field, offset=offset)

        self.size = size


class ExtraneousDataError(DeserializationError):
    """Extra bytes were found at the end of the input after deserialization."""
