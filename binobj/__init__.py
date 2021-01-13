"""
binobj
======

A Python library for reading and writing structured binary data.
"""

import pkg_resources as _pkgr

from .errors import *
from .fields import *
from .structures import *


def __to_version_info():
    parts = _pkgr.parse_version(__version__)
    base = parts.base_version
    return (*map(int, base.split(".")), (parts.public[len(base) :].lstrip(".") or None))


# Do not modify directly; use ``bumpversion`` command instead.
__version__ = "0.10.0"
__version_info__ = __to_version_info()
