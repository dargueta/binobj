"""Fields representing strings and byte sequences."""

from __future__ import annotations

import codecs
import enum
import io
import uuid
from typing import TYPE_CHECKING

from typing_extensions import override

from binobj import errors
from binobj import helpers
from binobj.fields.base import Field


if TYPE_CHECKING:  # pragma: no cover
    from typing import Any
    from typing import BinaryIO
    from typing import Optional

    from binobj.typedefs import StrDict


__all__ = ["Bytes", "String", "StringZ", "UUID4", "UUIDFormat"]


class Bytes(Field[bytes]):
    """Raw binary data."""

    @override
    def _do_load(
        self, stream: BinaryIO, context: object, loaded_fields: StrDict
    ) -> Optional[bytes]:
        return self._read_exact_size(stream, loaded_fields)

    @override
    def _do_dump(
        self, stream: BinaryIO, data: bytes, context: object, all_fields: StrDict
    ) -> None:
        write_size = self.get_expected_size(all_fields)
        if len(data) != write_size:
            raise errors.ValueSizeError(field=self, value=data)

        stream.write(data)

    def _size_for_value(self, value: bytes) -> int:
        return len(value)


class String(Field[str]):
    """A fixed-length string.

    :param int size:
        The field's size in *bytes*, not *characters*. For most text encodings these are
        the same, but some encodings use multiple bytes per character.

    :param str encoding:
        The encoding to use for converting the string to and from bytes. Defaults to
        `ISO 8859-1`_.

    :param bytes pad_byte:
        A single byte to use as padding for strings that are too short to fit into the
        field. If not given, strings that aren't exactly ``size`` bytes when encoded
        will trigger a :class:`~binobj.errors.ValueSizeError`.

        .. versionadded:: 0.2.0

    .. note ::
        The ``utf-8-sig``, ``utf-16``, and ``utf-32`` codecs add a `byte order mark`_
        (BOM) at the beginning of the string, so you'll need to take those extra bytes
        into account when defining this field size. Alternatively, you can use the
        codecs' variants that don't add the BOM, such as ``utf-16-le`` or ``utf-16-be``.

    .. _byte order mark: https://en.wikipedia.org/wiki/Byte_order_mark
    .. _ISO 8859-1: https://en.wikipedia.org/wiki/ISO/IEC_8859-1
    """

    def __init__(
        self,
        *,
        encoding: str = "iso-8859-1",
        pad_byte: Optional[bytes] = None,
        **kwargs: Any,
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

    @override
    def _do_load(
        self, stream: BinaryIO, context: object, loaded_fields: StrDict
    ) -> Optional[str]:
        """Load a fixed-length string from a stream."""
        to_load = self._read_exact_size(stream, loaded_fields)
        return to_load.decode(self.encoding)

    @override
    def _do_dump(
        self, stream: BinaryIO, data: str, context: object, all_fields: StrDict
    ) -> None:
        """Dump a fixed-length string into the stream."""
        stream.write(self._encode_and_resize(data, all_fields))

    def _encode_and_resize(self, string: str, all_fields: StrDict) -> bytes:
        """Encode a string and size it to this field.

        :param str string:
            The string to encode.
        :param dict all_fields:
            A dict of all fields that are being dumped. Used for calculating the length
            of the field if that depends on the value of another field.

        :return: ``string`` encoded as ``size`` bytes.
        :rtype: bytes
        """
        to_dump = string.encode(self.encoding)
        write_size = self.get_expected_size(all_fields)

        size_diff = len(to_dump) - write_size
        if size_diff > 0:
            # String is too long.
            raise errors.ValueSizeError(field=self, value=to_dump)
        if size_diff < 0:
            if self.pad_byte is None:
                # String is too short and we're not padding it.
                raise errors.ValueSizeError(field=self, value=to_dump)
            to_dump += self.pad_byte * -size_diff

        return to_dump

    def _add_padding(self, serialized: bytes, to_size: int) -> bytes:
        if self.pad_byte is None:
            raise errors.ValueSizeError(field=self, value=serialized)
        return serialized + self.pad_byte * (to_size - len(serialized))

    def _size_for_value(self, value: str) -> int:
        return len(value.encode(self.encoding))


class StringZ(String):
    """A variable-length null-terminated string.

    The terminating null is guaranteed to be the proper size for multibyte encodings.
    """

    @override
    def _do_load(
        self, stream: BinaryIO, context: object, loaded_fields: StrDict
    ) -> str:
        max_bytes: Optional[int]
        try:
            max_bytes = self.get_expected_size(loaded_fields)
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

    @override
    def _do_dump(
        self, stream: BinaryIO, data: str, context: object, all_fields: StrDict
    ) -> None:
        stream.write((data + "\0").encode(self.encoding))

    def _size_for_value(self, value: str) -> int:
        return len((value + "\0").encode(self.encoding))


class UUIDFormat(enum.Enum):
    """The storage format of a UUID4."""

    BINARY_VARIANT_1 = "binary_var_1"
    """The binary format, RFC-4122 variant 1.

    The UUID4 is stored as a 16-byte sequence of big-endian integers. This is the most
    common format used today.
    """

    BINARY_VARIANT_2 = "binary_var_2"
    """The binary format, RFC-4122 variant 2.

    The UUID4 is stored as a 16-byte sequence of integers in mixed-endian format. This
    is described in the RFC as "Microsoft Corporation backward compatibility format". As
    the name suggests, this is pretty much only used by Microsoft software.
    """

    CANONICAL_STRING = "canonical_string"
    """The canonical string representation of a UUID4.

    An example would be the ASCII string "4fcd056d-f29b-4cb8-8e37-99ab1b56a555".
    """

    HEX_STRING = "hex_string"
    """Like :attr:`.CANONICAL_STRING` but without dashes."""


class UUID4(Field[uuid.UUID]):
    """A UUID, version 4 (the most common nowadays).

    .. versionadded:: 0.11.0
    """

    size: int

    def __init__(
        self, *, stored_as: UUIDFormat = UUIDFormat.BINARY_VARIANT_1, **kwargs: Any
    ):
        self.stored_as = stored_as
        if stored_as in (UUIDFormat.BINARY_VARIANT_1, UUIDFormat.BINARY_VARIANT_2):
            size = 16
        elif stored_as is UUIDFormat.CANONICAL_STRING:
            size = 36
        elif stored_as is UUIDFormat.HEX_STRING:
            size = 32
        else:  # pragma: no cover
            raise NotImplementedError(
                f"BUG: The UUID4 storage format {stored_as!r} isn't implemented. Please"
                " file a bug report."
            )
        super().__init__(size=size, **kwargs)

    @override
    def _do_load(
        self, stream: BinaryIO, context: object, loaded_fields: StrDict
    ) -> Optional[uuid.UUID]:
        raw_data = stream.read(self.size)
        if len(raw_data) < self.size:
            raise errors.UnexpectedEOFError(
                field=self, size=self.size, offset=stream.tell()
            )

        if self.stored_as is UUIDFormat.BINARY_VARIANT_1:
            return uuid.UUID(bytes=raw_data)
        if self.stored_as is UUIDFormat.BINARY_VARIANT_2:
            return uuid.UUID(bytes_le=raw_data)
        return uuid.UUID(hex=raw_data.decode("ascii"))

    @override
    def _do_dump(
        self, stream: BinaryIO, data: uuid.UUID, context: object, all_fields: StrDict
    ) -> None:
        if self.stored_as is UUIDFormat.BINARY_VARIANT_1:
            to_write = data.bytes
        elif self.stored_as is UUIDFormat.BINARY_VARIANT_2:
            to_write = data.bytes_le
        elif self.stored_as is UUIDFormat.CANONICAL_STRING:
            to_write = str(data).encode("ascii")
        else:
            to_write = data.hex.encode("ascii")

        stream.write(to_write)
