"""Definitions of aliases for common type annotations."""

import typing
from typing import Any
from typing import Callable
from typing import Mapping
from typing import MutableMapping
from typing import Optional
from typing import Type
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
MethodFieldValidator = Callable[["Struct", "Field[Any]", Any], Optional[bool]]
StructValidator = Callable[["Struct", StrDict], Optional[bool]]
FieldOrName = Union[str, "Field[Any]"]
StructOrName = Union[str, "Struct", Type["Struct"]]
