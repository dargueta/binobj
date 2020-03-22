"""Fields representing numeric values, such as integers and floats."""

import datetime
import struct
import sys

from binobj import errors
from binobj import helpers
from binobj import varints
from binobj.fields.base import Field


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


class Float(Field):
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

    def __init__(self, *, format_string, endian=None, **kwargs):
        if format_string == "e" and sys.version_info[:2] < (3, 6):
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

    def _do_load(self, stream, context, loaded_fields):
        data = self._read_exact_size(stream)
        try:
            return struct.unpack(self.format_string, data)[0]
        except struct.error as exc:
            raise errors.DeserializationError(message=str(exc), field=self, data=data)

    def _do_dump(self, stream, data, context, all_fields):
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

    def __init__(self, **kwargs):
        super().__init__(format_string="e", **kwargs)


class Float32(Float):
    """A single-precision floating-point number in IEEE-754 `binary32`_ format.

    .. _binary32: https://en.wikipedia.org/wiki/Single-precision_floating-point_format
    """

    def __init__(self, **kwargs):
        super().__init__(format_string="f", **kwargs)


class Float64(Float):
    """A floating-point number stored in IEEE-754 `binary64`_ format.

    .. _binary64: https://en.wikipedia.org/wiki/Double-precision_floating-point_format
    """

    def __init__(self, **kwargs):
        super().__init__(format_string="d", **kwargs)


class Integer(Field):
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

    .. _signed formats: https://en.wikipedia.org/wiki/Signed_number_representations
    """

    def __init__(self, *, endian=None, signed=True, **kwargs):
        super().__init__(**kwargs)
        self.endian = endian or sys.byteorder
        self.signed = signed

    def _do_load(self, stream, context, loaded_fields):
        """Load an integer from the given stream."""
        return helpers.read_int(stream, self.size, self.signed, self.endian)

    def _do_dump(self, stream, data, context, all_fields):
        """Dump an integer to the given stream."""
        try:
            return helpers.write_int(stream, data, self.size, self.signed, self.endian)
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

    def __init__(self, *, vli_format, max_bytes=None, **kwargs):
        encoding_info = varints.INTEGER_ENCODING_MAP.get(vli_format)

        if encoding_info is None:
            raise errors.ConfigurationError(
                "Invalid or unsupported integer encoding scheme: %r" % vli_format,
                field=self,
            )

        format_endianness = encoding_info["endian"]
        format_signedness = encoding_info["signed"]

        super().__init__(endian=format_endianness, signed=format_signedness, **kwargs)

        self.vli_format = vli_format
        self.max_bytes = max_bytes
        self._encode_integer_fn = encoding_info["encode"]
        self._decode_integer_fn = encoding_info["decode"]

    def _do_load(self, stream, context, loaded_fields):
        """Load a variable-length integer from the given stream."""
        return self._decode_integer_fn(stream)

    def _do_dump(self, stream, data, context, all_fields):
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

    def _size_for_value(self, value):
        return len(self._encode_integer_fn(value))


class UnsignedInteger(Integer):
    """An unsigned two's-complement integer of some fixed size.

    This class is typically not used directly, except for integers with sizes
    that aren't powers of two, e.g. for a 24-bit number.

    .. seealso:: :class:`.Integer`
    """

    def __init__(self, **kwargs):
        super().__init__(signed=False, **kwargs)


class Int8(Integer):
    """An 8-bit signed integer."""

    def __init__(self, **kwargs):
        super().__init__(size=1, **kwargs)


class Int16(Integer):
    """A 16-bit signed integer."""

    def __init__(self, **kwargs):
        super().__init__(size=2, **kwargs)


class Int32(Integer):
    """A 32-bit signed integer."""

    def __init__(self, **kwargs):
        super().__init__(size=4, **kwargs)


class Int64(Integer):
    """A 64-bit signed integer."""

    def __init__(self, **kwargs):
        super().__init__(size=8, **kwargs)


class UInt8(Int8):
    """An 8-bit unsigned integer."""

    def __init__(self, **kwargs):
        super().__init__(signed=False, **kwargs)


class UInt16(Int16):
    """A 16-bit unsigned integer."""

    def __init__(self, **kwargs):
        super().__init__(signed=False, **kwargs)


class UInt32(Int32):
    """A 32-bit unsigned integer."""

    def __init__(self, **kwargs):
        super().__init__(signed=False, **kwargs)


class UInt64(Int64):
    """A 64-bit unsigned integer."""

    def __init__(self, **kwargs):
        super().__init__(signed=False, **kwargs)


class Timestamp(Integer):
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

    .. versionadded:: 0.6.0

    .. _Unix epoch: https://en.wikipedia.org/wiki/Unix_time
    .. seealso:: :class:`.Timestamp32`, :class:`.Timestamp64`
    """
    _RESOLUTION_UNITS = {"s": 1, "ms": 1e3, "us": 1e6, "ns": 1e9}

    def __init__(self, *, resolution="s", tz_aware=False, **kwargs):
        super().__init__(**kwargs)
        if resolution not in self._RESOLUTION_UNITS:
            raise errors.ConfigurationError(
                "Invalid resolution. Expected one of %s but got %r"
                % (", ".join(repr(k) for k in self._RESOLUTION_UNITS), resolution),
                field=self,
            )

        self.resolution = resolution
        self.tz_aware = tz_aware
        self._units = self._RESOLUTION_UNITS[resolution]

    def _do_load(self, stream, context, loaded_fields):
        value = super()._do_load(stream, context, loaded_fields)
        if not self.tz_aware:
            return datetime.datetime.fromtimestamp(value / self._units)
        return datetime.datetime.fromtimestamp(
            value / self._units, datetime.timezone.utc
        )

    def _do_dump(self, stream, data, context, all_fields):
        timestamp = int(data.timestamp() * self._units)
        super()._do_dump(stream, timestamp, context, all_fields)


class Timestamp32(Timestamp):
    """A timestamp saved as a 32-bit integer.

    .. versionadded:: 0.6.0
    .. seealso:: :class:`.Timestamp`
    """

    def __init__(self, **kwargs):
        super().__init__(size=4, **kwargs)


class Timestamp64(Timestamp):
    """A timestamp saved as a 64-bit integer.

    .. versionadded:: 0.6.0
    .. seealso:: :class:`.Timestamp`
    """

    def __init__(self, **kwargs):
        super().__init__(size=8, **kwargs)
