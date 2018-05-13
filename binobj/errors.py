"""Errors for the binobj package."""


class Error(Exception):
    """Base class for all binobj errors.

    Do not throw this exception directly.
    """
    # pylint: disable=keyword-arg-before-vararg
    def __init__(self, message=None, *args):
        # If there is no error message, use the first line of the docstring.
        if message is None:
            message = self.__doc__.splitlines()[0]
        super().__init__(message, *args)


class ConfigurationError(Error):
    """A field, struct, or other object was misconfigured.

    At least one of the ``field``, ``struct``, or ``obj`` keyword arguments must
    be passed to the constructor.

    :param str message:
        Optional. A description of what's wrong. If not given, a generic error
        message will be chosen depending on which of the ``field``, ``struct``,
        or ``obj`` keyword arguments is passed.
    :param field:
        The misconfigured :class:`~binobj.fields.Field` or its name.
    :param struct:
        The misconfigured :class:`~binobj.structures.Struct` or its name.
    :param obj:
        If the misconfigured object is neither a field nor a struct, pass it or
        its name here.

    .. versionadded:: 0.3.0

        The ``struct`` and ``obj`` arguments.

    :raise ValueError:
        None of the ``field``, ``struct``, or ``obj`` keyword arguments were
        passed.
    """
    def __init__(self, message=None, *, field=None, struct=None, obj=None):
        if not (field or struct or obj):
            raise ValueError('At least one of `field`, `struct`, or `obj` must '
                             'be passed to the constructor.')

        if not message:
            if field:
                if struct:
                    message = 'Field {f!r} in struct {s!r} was misconfigured.'
                else:
                    message = 'The field {f!r} was misconfigured.'
            elif struct:
                message = 'The struct {s!r} was misconfigured.'
            else:
                message = 'The object {o!r} was misconfigured.'

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
    """An error occurred while computing a field reference.

    :param str message:
        Optional. A more detailed error message, if desired.
    :param str field:
        The name of the field that failed to be referenced.
    """
    def __init__(self, message=None, *, field):
        super().__init__(message)
        self.field = field


class IllegalOperationError(Error):
    """The attempted operation is disallowed.

    .. versionadded:: 0.4.1
    """


################################################################################


class ImmutableFieldError(IllegalOperationError):
    """Cannot assign to an immutable or computed field.

    .. versionadded:: 0.4.1
    """


class MultipleInheritanceError(ConfigurationError):
    """A Struct can't inherit from more than one Struct, since the field order
    could be ambiguous.

    .. versionadded:: 0.3.0
    """


class FieldRedefinedError(ConfigurationError):
    """A struct has a field already defined in a parent class.

    :param str struct:
        The name of the struct that has the redefined field.
    :param field:
        The :class:`~binobj.fields.Field` that's been redefined, or its name.

    .. versionadded:: 0.3.0
    """
    def __init__(self, *, struct, field):
        super().__init__(
            'Struct %s defines field %r already defined in its parent class.'
            % (struct, field), struct=struct, field=field)


class UndefinedSizeError(ConfigurationError):
    """The size of the field couldn't be determined, possibly due to misconfiguration.

    :param field:
        The :class:`~binobj.fields.Field` that's missing its size, or the name
        of that field.

    .. versionadded:: 0.3.1
    """
    def __init__(self, *, field):
        super().__init__(
            "Size of field %r couldn't be determined. The field might not have "
            "had its `size` set, or a variable-sized field has a bug."
            % field, field=field)


class UnserializableValueError(SerializationError):
    """The value couldn't be serialized.

    :param ~binobj.fields.Field field:
        The field that failed to serialize the given value.
    :param value:
        The value that can't be serialized.
    :param str reason:
        Optional. The reason for the failure.
    """
    def __init__(self, *, field, value, reason=None):
        if reason is not None:
            message = "%s can't serialize value: %s" % (field, reason)
        else:
            message = "%s can't serialize value of type %r." \
                      % (field, type(value).__name__)
        super().__init__(message, field=field, value=value)


class MissingRequiredValueError(SerializationError):
    """No value was passed for a required field.

    :param field:
        The missing field, or its name.
    """
    def __init__(self, *, field):
        super().__init__('Missing required value for field: %s' % field,
                         field=field)


class UnexpectedValueError(SerializationError):
    """The data to dump has unexpected fields.

    :param ~binobj.structures.Struct struct:
        The struct performing the serialization.
    :param name:
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
    """The value can't be serialized because it doesn't fit into the field.

    :param ~binobj.fields.Field field:
        The field that failed to serialize the given value.
    :param value:
        The value that's too big.
    """
    def __init__(self, *, field, value):
        super().__init__(reason="Value doesn't fit into %r bytes." % field.size,
                         field=field, value=value)


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
