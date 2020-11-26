"""Fields representing numeric values, such as integers and floats."""

import datetime
import struct
import sys
import typing
from typing import Any
from typing import BinaryIO
from typing import Callable
from typing import Optional

from binobj import errors
from binobj import helpers
from binobj import varints
from binobj.fields.base import Field
from binobj.typedefs import StrDict
from binobj.varints import VarIntEncoding


__all__ = [
    "Float",
    "Float16",
    "Float32",
    "Float64",
    "Int8",
    "Int16",
    "Int32",
    "Int64",
    "Integer",
    "Timestamp",
    "Timestamp32",
    "Timestamp64",
    "UInt8",
    "UInt16",
    "UInt32",
    "UInt64",
    "UnsignedInteger",
    "VariableLengthInteger",
]


class Float(Field[float]):
    """A floating-point number in IEEE-754:2008 interchange format.

    This is a base class and should not be used directly.

    :param str format_string:
        The `format character`_ used by the :mod:`struct` library to load and
        dump this floating-point number. Can be "f" (32 bits) or "d" (64 bits);
        Python 3.6 and up support "e" (16 bits). Any other values will cause an
        error.
    :param str endian:
        The endianness to use to load/store the float. Either "big" or "little".
        If not given, defaults to the system's native byte ordering as given by
        :data:`sys.byteorder`.

    .. _format character: https://docs.python.org/3/library/struct.html#format-characters
    """

    def __init__(
        self, *, format_string: str, endian: Optional[str] = None, **kwargs: Any
    ):
        if format_string == "e" and sys.version_info[:2] < (3, 6):  # pragma: no cover
            raise errors.ConfigurationError(
                "binary16 format not supported on this version of Python.", field=self
            )
        super().__init__(size=struct.calcsize(format_string), **kwargs)

        self.endian = endian or sys.byteorder
        if self.endian == "big":
            self.format_string = ">" + format_string
        elif self.endian == "little":
            self.format_string = "<" + format_string
        else:
            raise errors.ConfigurationError(
                "`endian` must be 'big' or 'little', got %r." % endian, field=self
            )

    def _do_load(self, stream: BinaryIO, context: Any, loaded_fields: StrDict) -> float:
        data = self._read_exact_size(stream)
        try:
            return struct.unpack(self.format_string, data)[0]
        except struct.error as exc:
            raise errors.DeserializationError(message=str(exc), field=self, data=data)

    def _do_dump(
        self, stream: BinaryIO, data: Optional[float], context: Any, all_fields: StrDict
    ) -> None:
        try:
            serialized = struct.pack(self.format_string, data)
        except struct.error as exc:
            raise errors.SerializationError(message=str(exc), field=self)
        stream.write(serialized)


class Float16(Float):
    """A half-precision floating-point number in IEEE-754 `binary16`_ format.

    .. warning::
        This format is only supported on Python 3.6 and newer. Using this field
        in older versions of Python will crash.

    .. _binary16: https://en.wikipedia.org/wiki/Half-precision_floating-point_format
    """

    def __init__(self, **kwargs: Any):
        super().__init__(format_string="e", **kwargs)


class Float32(Float):
    """A single-precision floating-point number in IEEE-754 `binary32`_ format.

    .. _binary32: https://en.wikipedia.org/wiki/Single-precision_floating-point_format
    """

    def __init__(self, **kwargs: Any):
        super().__init__(format_string="f", **kwargs)


class Float64(Float):
    """A floating-point number stored in IEEE-754 `binary64`_ format.

    .. _binary64: https://en.wikipedia.org/wiki/Double-precision_floating-point_format
    """

    def __init__(self, **kwargs: Any):
        super().__init__(format_string="d", **kwargs)


class Integer(Field[int]):
    """A two's-complement integer of some fixed size.

    This class is typically not used directly, except for integers with sizes
    that aren't powers of two, e.g. for a 24-bit number.

    :param str endian:
        The endianness to use to load/store the integer. Either 'big' or 'little'.
        If not given, defaults to the system's native byte ordering as given by
        :data:`sys.byteorder`.
    :param bool signed:
        Indicates if this number is a two's-complement signed or unsigned integer.
        Defaults to ``True`` (signed). `Signed formats`_ other than two's-complement
        such as sign-magnitude are not supported.
    :param int size:
        The size of the integer, in bytes.

        .. versionchanged:: 0.8.0
            The ``size`` argument is now required.

    .. versionchanged:: 0.8.0
        The class now throws :class:`UndefinedSizeError` when loading and dumping if
        the field doesn't have a defined size. Before it used to crash with a TypeError
        due to this oversight.

    .. _signed formats: https://en.wikipedia.org/wiki/Signed_number_representations
    """

    __overrideable_attributes__ = ("endian",)

    def __init__(
        self, *, endian: Optional[str] = None, signed: bool = True, **kwargs: Any
    ):
        super().__init__(**kwargs)
        self.endian = endian or sys.byteorder
        self.signed = signed

    def _do_load(self, stream: BinaryIO, context: Any, loaded_fields: StrDict) -> int:
        """Load an integer from the given stream."""
        if not self.has_fixed_size:
            raise errors.UndefinedSizeError(field=self)
        return helpers.read_int(
            stream, self.get_expected_size(loaded_fields), self.signed, self.endian
        )

    def _do_dump(
        self, stream: BinaryIO, data: int, context: Any, all_fields: StrDict
    ) -> None:
        """Dump an integer to the given stream."""
        dump_size = self._size_for_value(data)
        if dump_size is None:
            raise errors.UndefinedSizeError(field=self)
        try:
            helpers.write_int(stream, data, dump_size, self.signed, self.endian)
        except (ValueError, OverflowError) as err:
            raise errors.UnserializableValueError(
                field=self, value=data, reason=str(err)
            )


class VariableLengthInteger(Integer):
    """An integer of varying size.

    :param VarIntEncoding vli_format:
        Required. The encoding to use for the variable-length integer.
    :param int max_bytes:
        The maximum number of bytes to use for encoding this integer. If not
        given, there's no restriction on the size.
    """

    def __init__(
        self,
        *,
        vli_format: VarIntEncoding,
        max_bytes: Optional[int] = None,
        **kwargs: Any
    ):
        encoding_info = varints.INTEGER_ENCODING_MAP.get(vli_format)

        if encoding_info is None:
            raise errors.ConfigurationError(
                "Invalid or unsupported integer encoding scheme: %r" % vli_format,
                field=self,
            )

        format_endianness = typing.cast(str, encoding_info["endian"])
        format_signedness = typing.cast(bool, encoding_info["signed"])

        self.vli_format = vli_format
        self.max_bytes = max_bytes
        self._encode_integer_fn = typing.cast(
            Callable[[int], bytes], encoding_info["encode"]
        )
        self._decode_integer_fn = typing.cast(
            Callable[[BinaryIO], int], encoding_info["decode"]
        )
        super().__init__(endian=format_endianness, signed=format_signedness, **kwargs)

    def _do_load(self, stream: BinaryIO, context: Any, loaded_fields: StrDict) -> int:
        """Load a variable-length integer from the given stream."""
        return self._decode_integer_fn(stream)

    def _do_dump(
        self, stream: BinaryIO, data: int, context: Any, all_fields: StrDict
    ) -> None:
        """Dump an integer to the given stream."""
        try:
            encoded_int = self._encode_integer_fn(data)
        except (ValueError, OverflowError) as err:
            raise errors.UnserializableValueError(
                field=self, value=data, reason=str(err)
            )

        if self.max_bytes is not None and len(encoded_int) > self.max_bytes:
            raise errors.ValueSizeError(field=self, value=data)

        stream.write(encoded_int)

    def _size_for_value(self, value: Optional[int]) -> int:
        if value is None:
            return len(self._get_null_repr())
        return len(self._encode_integer_fn(value))


class UnsignedInteger(Integer):
    """An unsigned two's-complement integer of some fixed size.

    This class is typically not used directly, except for integers with sizes
    that aren't powers of two, e.g. for a 24-bit number.

    .. seealso:: :class:`.Integer`
    """

    def __init__(self, **kwargs: Any):
        super().__init__(signed=False, **kwargs)


class Int8(Integer):
    """An 8-bit signed integer."""

    def __init__(self, **kwargs: Any):
        super().__init__(size=1, **kwargs)


class Int16(Integer):
    """A 16-bit signed integer."""

    def __init__(self, **kwargs: Any):
        super().__init__(size=2, **kwargs)


class Int32(Integer):
    """A 32-bit signed integer."""

    def __init__(self, **kwargs: Any):
        super().__init__(size=4, **kwargs)


class Int64(Integer):
    """A 64-bit signed integer."""

    def __init__(self, **kwargs: Any):
        super().__init__(size=8, **kwargs)


class UInt8(Int8):
    """An 8-bit unsigned integer."""

    def __init__(self, **kwargs: Any):
        super().__init__(signed=False, **kwargs)


class UInt16(Int16):
    """A 16-bit unsigned integer."""

    def __init__(self, **kwargs: Any):
        super().__init__(signed=False, **kwargs)


class UInt32(Int32):
    """A 32-bit unsigned integer."""

    def __init__(self, **kwargs: Any):
        super().__init__(signed=False, **kwargs)


class UInt64(Int64):
    """A 64-bit unsigned integer."""

    def __init__(self, **kwargs: Any):
        super().__init__(signed=False, **kwargs)


class Timestamp(Field[datetime.datetime]):
    r"""A timestamp stored as an integer offset from the `Unix epoch`_.

    Timestamps are stored in UTC. When dumping, naive datetimes are assumed to
    be in the local timezone; when loading and ``tz_aware`` is False, loaded
    datetimes are in the local timezone.

    This class is typically not used directly, except for timestamps with sizes
    that aren't powers of two, e.g. the 96-bit timestamps used by Amazon
    Redshift.

    :param str resolution:
        The resolution timestamps will be stored with. Accepted values are "s",
        "ms", "us" (microseconds), and "ns". Note that Python's
        :class:`~datetime.datetime` objects don't support nanosecond resolution.
    :param bool tz_aware:
        Controls whether loads return timezone-aware or naive
        :class:`~datetime.datetime`\s. Loaded timestamps are naive by default,
        and in the platform's local timezone.

        .. code-block:: python

            >>> field = Timestamp32(tz_aware=True)
            >>> field.from_bytes(b'\xa3\xc3\x55\x5c')
            datetime.datetime(2019, 2, 2, 16, 21, 55, tzinfo=datetime.timezone.utc)
    :param str endian:
        The byte order to store the timestamp in. Defaults to the host machine's byte
        order as given by :data:`sys.byteorder`.
    :param bool signed:
        Whether the timestamp should be stored as a signed integer or not. It's highly
        recommended this be left at the default (True) for compatibility with other
        Unix systems.

    .. versionadded:: 0.6.0
    .. versionchanged:: 0.8.0

        * This class no longer inherits from :class:`Integer`.
        * ``size`` is now a required argument.
        * The class throws :class:`UndefinedSizeError` when loading and dumping if the
          field doesn't have a defined size. Before it used to crash with a TypeError
          due to this oversight.

    .. _Unix epoch: https://en.wikipedia.org/wiki/Unix_time
    .. seealso:: :class:`.Timestamp32`, :class:`.Timestamp64`
    """

    _RESOLUTION_UNITS = {"s": 1, "ms": 1e3, "us": 1e6, "ns": 1e9}

    def __init__(
        self,
        *,
        size: int,
        resolution: str = "s",
        tz_aware: bool = False,
        endian: Optional[str] = None,
        signed: bool = True,
        **kwargs: Any
    ):
        if resolution not in self._RESOLUTION_UNITS:
            raise errors.ConfigurationError(
                "Invalid resolution. Expected one of %s but got %r"
                % (", ".join(repr(k) for k in self._RESOLUTION_UNITS), resolution),
                field=self,
            )

        super().__init__(size=size, **kwargs)

        self.endian = endian or sys.byteorder
        self.signed = signed
        self.resolution = resolution
        self.tz_aware = tz_aware
        self._units = self._RESOLUTION_UNITS[resolution]

    def _do_load(
        self, stream: BinaryIO, context: Any, loaded_fields: StrDict
    ) -> datetime.datetime:
        value = helpers.read_int(
            stream, self.get_expected_size(loaded_fields), self.signed, self.endian
        )
        if not self.tz_aware:
            return datetime.datetime.fromtimestamp(value / self._units)
        return datetime.datetime.fromtimestamp(
            value / self._units, datetime.timezone.utc
        )

    def _do_dump(
        self,
        stream: BinaryIO,
        data: datetime.datetime,
        context: Any,
        all_fields: StrDict,
    ) -> None:
        timestamp = int(data.timestamp() * self._units)
        try:
            helpers.write_int(
                stream,
                timestamp,
                self.get_expected_size(all_fields),
                self.signed,
                self.endian,
            )
        except (ValueError, OverflowError) as err:
            raise errors.UnserializableValueError(
                field=self, value=data, reason=str(err)
            )


class Timestamp32(Timestamp):
    """A timestamp saved as a 32-bit integer.

    .. versionadded:: 0.6.0
    .. seealso:: :class:`.Timestamp`
    """

    def __init__(self, **kwargs: Any):
        super().__init__(size=4, **kwargs)


class Timestamp64(Timestamp):
    """A timestamp saved as a 64-bit integer.

    .. versionadded:: 0.6.0
    .. seealso:: :class:`.Timestamp`
    """

    def __init__(self, **kwargs: Any):
        super().__init__(size=8, **kwargs)
