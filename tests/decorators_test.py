"""Unit tests for decorators."""

import pytest

import binobj
from binobj import errors
from binobj import fields


def test_computes__basic():
    """Basic test for using a computed field."""
    class Class(binobj.Struct):
        n_items = fields.UInt16(endian='little')
        items = fields.Array(fields.UInt16(endian='little'), count=n_items)

        @n_items.computes
        def _n_items(self, all_fields):     # pylint: disable=no-self-use
            return len(all_fields['items'])

    instance = Class(items=[10, 3, 255, 3])

    assert bytes(instance) == b'\x04\x00\x0a\x00\x03\x00\xff\x00\x03\x00'


def test_computes__rebind_fails():
    """You can't create two compute functions for a field."""
    with pytest.raises(errors.ConfigurationError):
        class Class(binobj.Struct):     # pylint: disable=unused-variable
            n_items = fields.UInt16(endian='little')
            items = fields.Array(fields.UInt16(endian='little'), count=n_items)

            @n_items.computes
            def _n_items(self, all_fields):     # pylint: disable=no-self-use
                return len(all_fields['items'])

            @n_items.computes
            def _n_items_2(self, all_fields):   # pylint: disable=no-self-use
                pass
