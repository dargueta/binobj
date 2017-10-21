"""
binobj
======

A Python library for reading and writing structured binary data.
"""
# pylint: disable=wildcard-import,unused-import

from .errors import *
from .fields import *
from .serialization import *
from .structures import *

__version_info__ = (0, 1, 0)
__version__ = '.'.join(str(v) for v in __version_info__)
