"""
binobj
======

A Python library for reading and writing structured binary data.
"""


# Do not modify directly; use ``bumpversion`` command instead.
__version__ = '0.5.0'
__version_info__ = tuple(int(p) for p in __version__.split('.'))


# pylint: disable=wildcard-import

from .errors import *
from .fields import *
from .structures import *
