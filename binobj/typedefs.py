"""Definitions of aliases for common type annotations."""
from __future__ import annotations

import typing
from collections.abc import Mapping
from collections.abc import MutableMapping
from typing import Any
from typing import Callable
from typing import Literal
from typing import Optional
from typing import TypeVar
from typing import Union


if typing.TYPE_CHECKING:  # pragma: no cover
    from binobj.fields.base import Field
    from binobj.structures import Struct


T_co = TypeVar("T_co", covariant=True, bound=object)

StrDict = Mapping[str, Any]
"""Any mapping using strings as the keys."""

MutableStrDict = MutableMapping[str, Any]
"""Any mutable mapping using strings for the keys."""

FieldValidator = Callable[["Field[Any]", Any], Optional[bool]]
"""A function that, given a field, returns True if it's valid and False otherwise."""

MethodFieldValidator = Callable[["Struct", "Field[Any]", Any], Optional[bool]]
"""A field validator that's a method in its containing struct."""

StructValidator = Callable[["Struct", StrDict], Optional[bool]]
"""A classmethod that validates an entire struct."""

FieldOrName = Union[str, "Field[Any]"]
"""A :class:`~binobj.fields.base.Field` object or its name."""

StructOrName = Union[str, "Struct", type["Struct"]]
"""A :class:`~binobj.structures.Struct` or its name."""

EndianString = Literal["little", "big"]
