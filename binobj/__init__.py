"""A Python library for reading and writing structured binary data."""

from __future__ import annotations

from typing import NamedTuple
from typing import Optional

from .errors import *
from .fields import *
from .pep526 import dataclass
from .structures import *


try:  # pragma: no cover (py<38)
    import importlib.metadata as _imp_meta
except ImportError:  # pragma: no cover (py38+)
    import importlib_metadata as _imp_meta  # type: ignore[no-redef]


class VersionInfo(NamedTuple):
    """Detailed information about the current version of the software."""

    major: int
    minor: int
    patch: int
    suffix: Optional[str]

    @classmethod
    def from_string(cls, version: str) -> VersionInfo:
        """Parse the version number string into a VersionInfo."""
        base_version, _, suffix = version.partition("-")
        major, minor, *_possibly_patch = base_version.split(".")
        if _possibly_patch:
            patch = _possibly_patch[0]
        else:
            patch = "0"
        return cls(int(major), int(minor), int(patch), suffix or None)

    def __str__(self) -> str:
        if self.suffix:
            return "%d.%d.%d-%s" % (self.major, self.minor, self.patch, self.suffix)
        return "%d.%d.%d" % (self.major, self.minor, self.patch)


__version__ = _imp_meta.version("binobj")
__version_info__ = VersionInfo.from_string(__version__)
