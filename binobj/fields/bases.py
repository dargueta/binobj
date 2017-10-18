"""Field type definitions."""

import operator

from binobj import errors
from binobj import serialization


class ValueOf:
    """A reference to the value of another field in the same struct.

    You can use this to make a property of one field depend on the value of
    another. For example, if you have a struct consisting of a two-byte integer
    ``length`` followed by a byte string ``data`` of ``length`` bytes, you can
    declare your struct like so::

        class MyStruct(Struct):
            length = UInt16()
            data = Bytes(n_bytes=ValueOf(length))

    Expressions are also possible::

        class BMPFile(Struct):
            signature = Const(b'BMP')
            width = UInt8()
            height = UInt8()
            pixels = Array(UInt8, count=ValueOf(width) * ValueOf(height))

    :param value_source:
        This argument can be one of the following:

        - A :class:`Field` object, as shown in the example.
        - The name of the field this object will refer to. This is mostly used
          for *forward references*, i.e. when a field relies on the value of one
          or more fields after it.
        - Another :class:`ValueOf` object. This is only necessary when building
          expressions and you generally won't need to do it yourself.

    :param operands:
        Internal use only. Only necessary when a :class:`ValueOf` is being used
        inside an expression. These are all the operands that the ``operator``
        will operate on. It's very rare to have more than two.

    :param callable xform_fn:
        Internal use only. The transform function to use when computing the full
        value of the expression. This is usually a callable that takes two
        arguments, depending on the type of operation.
    """
    def __init__(self, value_source, *operands, xform_fn=None):
        self.operands = operands    # type: List[Union[Field, ValueOf]]
        self.xform_fn = xform_fn    # type: callable
        self.using_field = None     # type: Field

        # These fields are set when the expression is bound.
        if isinstance(value_source, str):
            self.value_source_name = value_source   # type: str
            self.value_source = None                # type: Union[Field, ValueOf]
            self.struct_class = None                # type: type
        elif isinstance(value_source, Field):
            self.value_source_name = value_source.name
            self.value_source = value_source
            self.struct_class = value_source.struct_class
        elif isinstance(value_source, ValueOf):
            self.value_source_name = None
            self.value_source = value_source
            self.struct_class = value_source.struct_class
        else:
            TypeError("Unsupported value source: " + type(value_source).__name__)

    def bind(self, using_field):
        """Bind this expression to the field that uses it.

        :param Field using_field:
            The field that utilizes this reference, or a :class:`ValueOf`.
        """
        # Ignore an attempt to bind to None. This will happen when an unbound
        # field is used in an expression, such as in the example above. ``bind``
        # is called twice there -- once to build the expression, and a second
        # time to bind the expression to ``pixels``.
        if using_field is None:
            return

        if self.using_field is not None:
            raise RuntimeError(
                "This reference is already bound. A single reference object "
                "can't be used by multiple fields.")

        self.using_field = using_field
        self.struct_class = using_field.struct_class

        value_source = self.struct_class.__fields__.get(self.value_source_name)
        if value_source is None:
            raise errors.FieldConfigurationError(
                'No field named %r exists on %s.'
                % (self.value_source_name, self.struct_class.__name__),
                field=using_field)
        self.value_source = value_source

    def compute_for_dumping(self, data_dict):
        """Get the value of this field reference when dumping.

        :param dict data_dict:
            The data being serialized.

        :return: The value of the referenced field.
        """
        if self.value_source is None:
            raise RuntimeError('This reference is not bound to a field.')

        if isinstance(self.value_source, Field):
            computed_self = self._compute_dumping_field(data_dict)
        elif isinstance(self.value_source, ValueOf):
            computed_self = self._compute_dumping_valueof(data_dict)
        else:
            raise TypeError('Unsupported value source: %r' % self.value_source)

        return self.transform_for_dump(computed_self)

    def _compute_dumping_field(self, data_dict):
        if self.value_source_name in data_dict:
            return data_dict[self.value_source_name]
        elif self.value_source.__options__['required'] is True:
            raise errors.MissingRequiredValueError(field=self.value_source)
        return self.value_source.__options__['default']

    def _compute_dumping_valueof(self, data_dict):
        # TODO
        raise NotImplementedError

    def compute_for_loading(self, stream, offset, loaded_data, context):
        """Get the value of this field reference when loading.

        :param bitstring.BitStream stream:
            The bit stream this struct is being loaded from.
        :param int offset:
            The current offset in bits from the beginning of the struct.
        :param dict loaded_data:
            The data that's already been loaded.

        :return: The deserialized value of the referred field.

        :raise BadForwardReferenceError:
            This field references a field that occurs after it, but the target
            field isn't at a fixed offset and thus can't be located.
        """
        if self.value_source is None:
            raise RuntimeError('This reference is not bound to a field.')

        if isinstance(self.value_source, Field):
            computed_self = self._compute_loading_field(
                stream, offset, loaded_data, context)
        elif isinstance(self.value_source, ValueOf):
            computed_self = self._compute_loading_valueof(
                stream, offset, loaded_data, context)
        else:
            raise TypeError('Unsupported value source: %r' % self.value_source)

        return self.transform_for_load(computed_self)

    def _compute_loading_field(self, stream, offset, loaded_data, context):
        if self.value_source is None:
            raise RuntimeError('This reference is not bound to a field.')
        elif self.value_source_name in loaded_data:
            return loaded_data[self.value_source_name]
        elif self.value_source.offset is not None:
            # Field is at a fixed offset from the beginning of the struct. We
            # can pull it directly.
            absolute_offset = stream.pos
            stream.pos = absolute_offset - offset + self.value_source.offset
            try:
                return self.value_source.load(stream, context)
            finally:
                stream.pos = absolute_offset

        raise errors.BadForwardReferenceError(from_field=self.using_field,
                                              to_field=self.value_source)

    def _compute_loading_valueof(self, stream, offset, loaded_data, context):
        # TODO
        raise NotImplementedError

    def transform_for_load(self, computed_self):
        """Run the transform function on the computed value of the source field.

        :param computed_self:
            The computed value of the source field of this reference object
            after being loaded from the input stream.

        :return: The transformed value.
        """
        return self.xform_fn(computed_self, *self.operands)

    def transform_for_dump(self, computed_self):
        """Run the transform function on the computed value of the source field.

        :param computed_self:
            The computed value of the source field of this reference object
            right before being dumped into the destination stream.

        :return: The transformed value.
        """
        # FIXME (dargueta): This should differ from transform_form_load.
        return self.xform_fn(computed_self, *self.operands)

    def __abs__(self):
        source = type(self)(self, xform_fn=abs)
        source.bind(self.using_field)
        return source

    def __add__(self, other):
        source = type(self)(self, other, xform_fn=operator.add)
        source.bind(self.using_field)
        return source

    def __and__(self, other):
        source = type(self)(self, other, xform_fn=operator.and_)
        source.bind(self.using_field)
        return source

    # def __bool__(self):
    #     source = type(self)(self, xform_fn=bool)
    #     source.bind(self.using_field)
    #     return source

    def __contains__(self, item):
        source = type(self)(self, item, xform_fn=operator.contains)
        source.bind(self.using_field)
        return source

    def __float__(self):
        source = type(self)(self, xform_fn=float)
        source.bind(self.using_field)
        return source

    def __floordiv__(self, other):
        source = type(self)(self, other, xform_fn=operator.floordiv)
        source.bind(self.using_field)
        return source

    def __getitem__(self, item):
        source = type(self)(self, item, xform_fn=operator.getitem)
        source.bind(self.using_field)
        return source

    # def __index__(self):
    #     source = type(self)(self, xform_fn=int)
    #     source.bind(self.using_field)
    #     return source

    def __int__(self):
        source = type(self)(self, xform_fn=int)
        source.bind(self.using_field)
        return source

    def __invert__(self):
        source = type(self)(self, xform_fn=operator.invert)
        source.bind(self.using_field)
        return source

    # def __len__(self):  # pylint: disable=invalid-length-returned
    #     source = type(self)(self, xform_fn=len)
    #     source.bind(self.using_field)
    #     return source

    def __lshift__(self, other):
        source = type(self)(self, other, xform_fn=operator.lshift)
        source.bind(self.using_field)
        return source

    def __mod__(self, other):
        source = type(self)(self, other, xform_fn=operator.mod)
        source.bind(self.using_field)
        return source

    def __mul__(self, other):
        source = type(self)(self, other, xform_fn=operator.mul)
        source.bind(self.using_field)
        return source

    def __neg__(self):
        source = type(self)(self, xform_fn=operator.neg)
        source.bind(self.using_field)
        return source

    def __or__(self, other):
        source = type(self)(self, other, xform_fn=operator.or_)
        source.bind(self.using_field)
        return source

    def __pow__(self, power, modulo=None):
        raise NotImplementedError

    def __sub__(self, other):
        source = type(self)(self, other, xform_fn=operator.sub)
        source.bind(self.using_field)
        return source

    def __truediv__(self, other):
        source = type(self)(self, other, xform_fn=operator.truediv)
        source.bind(self.using_field)
        return source

    def __xor__(self, other):
        source = type(self)(self, other, xform_fn=operator.xor)
        source.bind(self.using_field)
        return source


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
            if isinstance(item, ValueOf):
                item.bind(self)

        super().__init__(allow_null=allow_null, null_value=null_value, **kwargs)

    def __str__(self):
        return '%s::%s(name=%r)' % (
            (self.struct_class.__name__, type(self).__name__, self.name))
