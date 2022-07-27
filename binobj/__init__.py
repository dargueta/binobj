"""A Python library for reading and writing structured binary data."""

from typing import Optional
from typing import Tuple

import pkg_resources as _pkgr

from .errors import *
from .fields import *
from .structures import *


def __to_version_info() -> Tuple[int, int, int, Optional[str]]:
    parts = _pkgr.parse_version(__version__)
    base = parts.base_version
    version_parts = tuple(map(int, base.split(".")))
    suffix_part = parts.public[len(base) :].lstrip(".") or None
    return version_parts[0], version_parts[1], version_parts[2], suffix_part


# Do not modify directly; use ``bumpversion`` command instead.
__version__ = "0.10.5"
__version_info__ = __to_version_info()
