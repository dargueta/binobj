"""Tests for declaring fields via PEP-526 variable annotations.

This file MUST be ignored by Python 3.5 tests. If not, importing it will trigger syntax
errors and you will be sad.
"""

from typing import ClassVar

import binobj
from binobj.pep586 import dataclass
from binobj import fields


@dataclass
class BasicClass(binobj.Struct):
    some_value: fields.UInt16
    string: fields.String(size=16, encoding="ibm500")
    other_string: fields.StringZ = "Default Value"
    ignored: ClassVar[int] = 1234


def test_field_extraction__basic():
    assert hasattr(BasicClass, "__annotations__")
    assert hasattr(BasicClass,"__binobj_struct__"), "Metadata not found on class"

    meta = BasicClass.__binobj_struct__
    assert meta.num_own_fields == 3, "Wrong number of fields detected"
    assert meta.components, "No components found."
    assert set(meta.components.keys()) == {"some_value", "string", "other_string"}

    assert BasicClass.other_string.default == "Default Value"
    assert BasicClass.string.encoding == "ibm500"
