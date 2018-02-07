import setuptools
import sys

# Thwart installation for unsupported versions of Python. `pip` didn't start
# enforcing `python_requires` until 9.0.
if sys.version_info < (3, 3):
    raise RuntimeError('Unsupported Python version: ' + sys.version)

setuptools.setup(setup_requires=['setuptools>=30.1.0'])
