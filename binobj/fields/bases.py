"""Field type definitions."""

from binobj import serialization


class Field(serialization.SerializableScalar):
    """The base class for all struct fields.

    :param str name:
        The name of the field.
    :param bool required:
        If ``True``, this value *must* be passed to the serializer for a struct.
        If ``False``, the default value will be used.
    :param bool allow_null:
        If ``True`` (the default) then ``None`` is an acceptable value to write
        for this field.
    :param bitstring.Bits null_value:
        A value to use to dump ``None``. When loading, the returned value will
        be ``None`` if this value is encountered.
    :param default:
        The default value to use if a value for this field isn't passed to the
        struct for serialization. If ``required`` is ``False`` and no default is
        given, null bytes will be used to fill the space required.
    :param bool discard:
        When deserializing, don't include this field in the returned results.
    """
    def __init__(self, *, name=None, required=True, allow_null=True,
                 null_value=serialization.DEFAULT, discard=False, **kwargs):
        if not allow_null and null_value is serialization.DEFAULT:
            null_value = serialization.UNDEFINED

        self.name = name
        self.required = required
        self.discard = discard

        # The following fields are set by the struct metaclass after the field
        # is instantiated.

        #: A weak reference to the `Struct` class containing this field.
        self.struct_class = None    # type: binobj.structures.Struct

        #: The zero-based index of the field in the struct.
        self.index = None   # type: int

        #: The zero-based bit offset of the field in the struct. If the offset
        #: can't be computed (e.g. it's preceded by a variable-length field),
        #: this will be ``None``.
        self.offset = None  # type: int

        # Some arguments and attributes may be references rather than actual
        # parameters. We must bind those references to this field.
        for item in vars(self):
            if isinstance(item, serialization.ValueOf):
                item.bind(self)

        super().__init__(allow_null=allow_null, null_value=null_value, **kwargs)

    def __str__(self):
        return '%s::%s(name=%r)' % (
            (self.struct_class.__name__, type(self).__name__, self.name))
