import sys

import setuptools


# Thwart installation for unsupported versions of Python. `pip` didn't start
# enforcing `python_requires` until 9.0.
if sys.version_info < (3, 5):
    raise RuntimeError("Unsupported Python version: " + sys.version)


# TODO (dargueta): Figure out why package detection in setup.cfg stopped working.
setuptools.setup(
    packages=setuptools.find_packages(exclude=["tests", "tests.*", "docs", "docs.*"])
)
