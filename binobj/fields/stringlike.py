"""Fields representing strings and byte sequences."""


import codecs
import io

from binobj import errors
from binobj.fields.base import Field
from binobj.fields.base import UNDEFINED
from binobj import helpers


__all__ = [
    'Bytes', 'String', 'StringZ',
]


class Bytes(Field):
    """Raw binary data."""
    def _do_load(self, stream, context, loaded_fields):
        return self._read_exact_size(stream)

    def _do_dump(self, stream, data, context, all_fields):
        if self.const is not UNDEFINED:
            stream.write(self.const)
            return

        if not isinstance(data, (bytes, bytearray)):
            raise errors.UnserializableValueError(field=self, value=data)
        elif self.size is not None and len(data) != self.size:
            raise errors.ValueSizeError(field=self, value=data)

        stream.write(data)

    def _size_for_value(self, value):
        return len(value)


class String(Field):
    """A fixed-length string.

    :param int size:
        The field's size in *bytes*, not *characters*. For most text encodings
        these are the same, but encodings use multiple bytes per character.

    :param str encoding:
        The encoding to use for converting the string to and from bytes. Defaults
        to ``'latin-1'``.

    :param bytes pad:
        A single byte to use as padding for strings that are too short to fit
        into the field. If not given, strings that aren't exactly ``size`` bytes
        when encoded will trigger a :class:`~binobj.errors.ValueSizeError`.

        .. versionadded:: 0.2.0

    .. note ::

        The ``utf-8-sig``, ``utf-16``, and ``utf-32`` codecs add a byte order
        marker (BOM) at the beginning of the string, so you'll need to take those
        extra bytes into account when defining this field size. Alternatively,
        you can use the codecs' variants that don't add the BOM, such as
        ``utf-16-le`` or ``utf-16-be``.
    """
    def __init__(self, *, encoding='latin-1', pad_byte=None, **kwargs):
        super().__init__(**kwargs)

        if pad_byte is not None:
            if not isinstance(pad_byte, (bytes, bytearray)):
                raise TypeError('`pad_byte` must be a bytes-like object.')
            elif len(pad_byte) != 1:
                raise ValueError('`pad_byte` must be exactly one byte long.')

        self.encoding = encoding
        self.pad_byte = pad_byte

    # pylint: disable=unused-argument

    def _do_load(self, stream, context, loaded_fields):
        """Load a fixed-length string from a stream."""
        to_load = self._read_exact_size(stream)
        return to_load.decode(self.encoding)

    def _do_dump(self, stream, data, context, all_fields):
        """Dump a fixed-length string into the stream."""
        if self.size is None:
            raise errors.UndefinedSizeError(field=self)

        stream.write(self._encode_and_resize(data))

    # pylint: enable=unused-argument

    def _encode_and_resize(self, string):
        """Encode a string and size it to this field.

        :param str string:
            The string to encode.

        :return: ``string`` encoded as ``size`` bytes.
        :rtype: bytes
        """
        to_dump = string.encode(self.encoding)

        if self.size is None:
            return to_dump

        size_diff = len(to_dump) - self.size
        if size_diff > 0:
            # String is too long.
            raise errors.ValueSizeError(field=self, value=to_dump)
        elif size_diff < 0:
            if self.pad_byte is None:
                # String is too short and we're not padding it.
                raise errors.ValueSizeError(field=self, value=to_dump)
            to_dump += self.pad_byte * -size_diff

        return to_dump

    def _size_for_value(self, value):
        return len(value.encode(self.encoding))


class StringZ(String):
    """A null-terminated string."""
    def _do_load(self, stream, context, loaded_fields):
        iterator = helpers.iter_bytes(stream, self.size)
        reader = codecs.iterdecode(iterator, self.encoding)
        result = io.StringIO()

        for char in reader:
            if char == '\0':
                return result.getvalue()
            result.write(char)

        # If we get out here then we hit EOF before getting to the null terminator.
        raise errors.DeserializationError(
            'Hit EOF before finding the trailing null.',
            field=self)

    def _do_dump(self, stream, data, context, all_fields):
        stream.write(self._encode_and_resize(data + '\0'))

    def _size_for_value(self, value):
        return len((value + '\0').encode(self.encoding))
