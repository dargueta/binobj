"""Unit tests for decorators."""

import pytest

import binobj
from binobj import decorators
from binobj import errors
from binobj import fields


def test_computes__basic():
    """Basic test for using a computed field."""

    class Class(binobj.Struct):
        n_items = fields.UInt16(endian="little")
        items = fields.Array(fields.UInt16(endian="little"), count=n_items)

        @n_items.computes
        def _n_items(self, all_fields):
            return len(all_fields["items"])

    instance = Class(items=[10, 3, 255, 3])

    assert bytes(instance) == b"\x04\x00\x0a\x00\x03\x00\xff\x00\x03\x00"


def test_computes__rebind_fails():
    """You can't create two compute functions for a field."""
    with pytest.raises(errors.ConfigurationError):

        class Class(binobj.Struct):
            n_items = fields.UInt16(endian="little")
            items = fields.Array(fields.UInt16(endian="little"), count=n_items)

            @n_items.computes
            def _n_items(self, all_fields):
                return len(all_fields["items"])

            @n_items.computes
            def _n_items_2(self, all_fields):
                pass


def test_computes__const_field_fails():
    """Can't set a compute function for a field with a defined const value."""
    with pytest.raises(errors.ConfigurationError):

        class Class(binobj.Struct):
            blah = fields.UInt16(const=1234)

            @blah.computes
            def _blah(self, all_fields):
                return 5678


def test_validates__crash_if_not_called():
    """Detonate if a validator decorator is used without calling."""
    with pytest.raises(TypeError) as errinfo:

        class Class(binobj.Struct):
            @decorators.validates
            def _n_items(self, all_fields):
                pass

    assert str(errinfo.value) == "Missing field name arguments."


def test_validates__crash_if_no_fields():
    """Detonate if a validator decorator is used with no field names."""
    with pytest.raises(TypeError) as errinfo:

        class Class(binobj.Struct):
            @decorators.validates()
            def _n_items(self, all_fields):
                pass

    assert str(errinfo.value) == "At least one field name must be given."


def test_validates__crash_if_not_strings():
    """Detonate if a validator decorator is used with one or more field names
    that aren't strings."""
    with pytest.raises(TypeError) as errinfo:

        class Class(binobj.Struct):
            n_items = fields.UInt16(endian="little")

            @decorators.validates(n_items)
            def _n_items(self, all_fields):
                pass

    assert "Do not pass Field objects." in str(errinfo.value)
