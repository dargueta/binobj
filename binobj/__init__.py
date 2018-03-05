"""
binobj
======

A Python library for reading and writing structured binary data.
"""
# pylint: disable=wildcard-import,unused-import

# Do not modify directly; use ``bumpversion`` command instead.
__version__ = '0.2.0'
__version_info__ = tuple(int(p) for p in __version__.split('.'))


from .errors import *
from .fields import *
from .structures import *
