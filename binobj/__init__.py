"""A Python library for reading and writing structured binary data."""

from __future__ import annotations

from typing import Optional
from typing import NamedTuple

import pkg_resources as _pkgr

from .errors import *
from .fields import *
from .structures import *


try:
    import importlib.metadata as _imp_meta
except ImportError:  # pragma: no cover (py38+)
    import importlib_metadata as _imp_meta


class VersionInfo(NamedTuple):
    """Detailed information about the current version of the software."""

    major: int
    minor: int
    patch: int
    suffix: Optional[str]

    @classmethod
    def from_string(cls, version: str) -> VersionInfo:
        parts = _pkgr.parse_version(version)
        base_version = parts.base_version
        major, minor, *_possibly_patch = base_version.split(".")
        if _possibly_patch:
            patch = _possibly_patch[0]
        else:
            patch = "0"

        suffix = parts.public[len(base_version) :].lstrip(".")
        return cls(int(major), int(minor), int(patch), suffix or None)

    def __str__(self) -> str:
        return "%d.%d.%d%s" % (self.major, self.minor, self.patch, self.suffix or "")


__version__ = _imp_meta.version("binobj")
__version_info__ = VersionInfo.from_string(__version__)
