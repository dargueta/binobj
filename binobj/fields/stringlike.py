"""Fields representing strings and byte sequences."""

import codecs
import io
from typing import Any
from typing import BinaryIO
from typing import Optional

from binobj import errors
from binobj import helpers
from binobj.fields.base import Field
from binobj.typedefs import StrDict


__all__ = ["Bytes", "String", "StringZ"]


class Bytes(Field[bytes]):
    """Raw binary data."""

    def _do_load(
        self, stream: BinaryIO, context: Any, loaded_fields: StrDict
    ) -> Optional[bytes]:
        return self._read_exact_size(stream, loaded_fields)

    def _do_dump(
        self, stream: BinaryIO, data: bytes, context: Any, all_fields: StrDict
    ) -> None:
        write_size = self.get_expected_size(all_fields)
        if len(data) != write_size:
            raise errors.ValueSizeError(field=self, value=data)

        stream.write(data)

    def _size_for_value(self, value: Optional[bytes]) -> int:
        if value is None:
            return len(self._get_null_repr())
        return len(value)


class String(Field[str]):
    """A fixed-length string.

    :param int size:
        The field's size in *bytes*, not *characters*. For most text encodings
        these are the same, but some encodings use multiple bytes per character.

    :param str encoding:
        The encoding to use for converting the string to and from bytes. Defaults
        to `ISO 8859-1`_.

    :param bytes pad_byte:
        A single byte to use as padding for strings that are too short to fit
        into the field. If not given, strings that aren't exactly ``size`` bytes
        when encoded will trigger a :class:`~binobj.errors.ValueSizeError`.

        .. versionadded:: 0.2.0

    .. note ::
        The ``utf-8-sig``, ``utf-16``, and ``utf-32`` codecs add a `byte order mark`_
        (BOM) at the beginning of the string, so you'll need to take those
        extra bytes into account when defining this field size. Alternatively,
        you can use the codecs' variants that don't add the BOM, such as
        ``utf-16-le`` or ``utf-16-be``.

    .. _byte order mark: https://en.wikipedia.org/wiki/Byte_order_mark
    .. _ISO 8859-1: https://en.wikipedia.org/wiki/ISO/IEC_8859-1
    """

    def __init__(
        self,
        *,
        encoding: str = "iso-8859-1",
        pad_byte: Optional[bytes] = None,
        **kwargs: Any
    ):
        if pad_byte is not None:
            if not isinstance(pad_byte, (bytes, bytearray)):
                raise errors.ConfigurationError(
                    "`pad_byte` must be a bytes-like object.", field=self
                )
            if len(pad_byte) != 1:
                raise errors.ConfigurationError(
                    "`pad_byte` must be exactly one byte long.", field=self
                )

        self.encoding = encoding
        self.pad_byte = pad_byte
        super().__init__(**kwargs)

    def _do_load(
        self, stream: BinaryIO, context: Any, loaded_fields: StrDict
    ) -> Optional[str]:
        """Load a fixed-length string from a stream."""
        to_load = self._read_exact_size(stream, loaded_fields)
        return to_load.decode(self.encoding)

    def _do_dump(
        self, stream: BinaryIO, data: str, context: Any, all_fields: StrDict
    ) -> None:
        """Dump a fixed-length string into the stream."""
        if self.size is None:
            raise errors.UndefinedSizeError(field=self)

        stream.write(self._encode_and_resize(data, all_fields))

    def _encode_and_resize(
        self, string: str, all_fields: Optional[StrDict] = None
    ) -> bytes:
        """Encode a string and size it to this field.

        :param str string:
            The string to encode.
        :param dict all_fields:
            Optional. A dict of all fields that are being dumped. Used for calculating
            the length of the field if that depends on the value of another field.

        :return: ``string`` encoded as ``size`` bytes.
        :rtype: bytes
        """
        if all_fields is None:
            all_fields = {}

        to_dump = string.encode(self.encoding)

        try:
            write_size = self.get_expected_size(all_fields)
        except errors.UndefinedSizeError:
            # The field has no defined size, so we don't care what we return. Delimited
            # strings like StringZ will cause this exception to be thrown, but it's not
            # an error.
            return to_dump

        size_diff = len(to_dump) - write_size

        # TODO (dargueta): Figure out why `field=self` gives MyPy indigestion below
        if size_diff > 0:
            # String is too long.
            raise errors.ValueSizeError(field=self, value=to_dump)
        if size_diff < 0:
            if self.pad_byte is None:
                # String is too short and we're not padding it.
                raise errors.ValueSizeError(field=self, value=to_dump)
            to_dump += self.pad_byte * -size_diff

        return to_dump

    def _size_for_value(self, value: Optional[str]) -> int:
        if value is None:
            return len(self._get_null_repr())
        return len(value.encode(self.encoding))


class StringZ(String):
    """A variable-length null-terminated string.

    The terminating null is guaranteed to be the proper size for multi-byte
    encodings.
    """

    def _do_load(self, stream: BinaryIO, context: Any, loaded_fields: StrDict) -> str:
        try:
            max_bytes = self.get_expected_size(loaded_fields)  # type: Optional[int]
        except errors.UndefinedSizeError:
            max_bytes = None

        iterator = helpers.iter_bytes(stream, max_bytes)
        reader = codecs.iterdecode(iterator, self.encoding)
        result = io.StringIO()

        for char in reader:
            if char == "\0":
                return result.getvalue()
            result.write(char)

        # If we get out here then we hit EOF before getting to the null terminator.
        raise errors.DeserializationError(
            "Hit EOF before finding the trailing null.", field=self
        )

    def _do_dump(
        self, stream: BinaryIO, data: str, context: Any, all_fields: StrDict
    ) -> None:
        stream.write(self._encode_and_resize(data + "\0"))

    def _size_for_value(self, value: Optional[str]) -> int:
        if value is None:
            return len(self._get_null_repr())
        return len((value + "\0").encode(self.encoding))
