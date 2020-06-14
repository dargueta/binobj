import typing
from typing import Any
from typing import Callable
from typing import Mapping
from typing import MutableMapping
from typing import Optional
from typing import TypeVar


if typing.TYPE_CHECKING:
    from binobj.fields.base import Field
    from binobj.structures import Struct


T_co = TypeVar("T_co", covariant=True, bound=object)

StrDict = Mapping[str, Any]
MutableStrDict = MutableMapping[str, Any]

FieldValidator = Callable[["Field[Any]", Any], Optional[bool]]
StructValidator = Callable[["Struct"], Optional[bool]]
