"""Definitions of aliases for common type annotations."""

from __future__ import annotations

import typing
from collections.abc import Callable
from collections.abc import Mapping
from collections.abc import MutableMapping
from typing import Any
from typing import Literal
from typing import Union


if typing.TYPE_CHECKING:  # pragma: no cover
    from typing import TypeAlias

    from binobj.fields.base import Field
    from binobj.structures import Struct


StrDict: TypeAlias = Mapping[str, Any]
"""Any mapping using strings as the keys."""

MutableStrDict: TypeAlias = MutableMapping[str, Any]
"""Any mutable mapping using strings for the keys."""

FieldValidator: TypeAlias = Callable[["Field[Any]", Any], bool | None]
"""A function that, given a field, returns True if it's valid and False otherwise."""

MethodFieldValidator: TypeAlias = Callable[["Struct", "Field[Any]", Any], bool | None]
"""A field validator that's a method in its containing struct."""

StructValidator: TypeAlias = Callable[["Struct", StrDict], bool | None]
"""A classmethod that validates an entire struct."""

FieldOrName: TypeAlias = Union[str, "Field[Any]"]
"""A :class:`~binobj.fields.base.Field` object or its name."""

StructOrName: TypeAlias = Union[str, "Struct", type["Struct"]]
"""A :class:`~binobj.structures.Struct` or its name."""

EndianString: TypeAlias = Literal["little", "big"]
