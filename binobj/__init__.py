"""A Python library for reading and writing structured binary data."""

from __future__ import annotations

import importlib.metadata
from typing import NamedTuple
from typing import Optional

from .errors import *
from .fields import *
from .pep526 import dataclass as dataclass
from .structures import *


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
        patch = _possibly_patch[0] if _possibly_patch else "0"
        return cls(int(major), int(minor), int(patch), suffix or None)

    def __str__(self) -> str:
        # Having a version suffix is rare for this library, so we'll tell pycoverage to
        # ignore this branch.
        if self.suffix:  # pragma: no cover
            return "%d.%d.%d-%s" % (self.major, self.minor, self.patch, self.suffix)
        return "%d.%d.%d" % (self.major, self.minor, self.patch)


__version__ = importlib.metadata.version("binobj")
__version_info__ = VersionInfo.from_string(__version__)
