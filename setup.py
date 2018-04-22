import setuptools
import sys

# Thwart installation for unsupported versions of Python. `pip` didn't start
# enforcing `python_requires` until 9.0.
if sys.version_info < (3, 4):
    raise RuntimeError('Unsupported Python version: ' + sys.version)


setuptools.setup(
    author='Diego Argueta',
    author_email='dargueta@users.noreply.github.com',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: Implementation :: CPython',
        'Programming Language :: Python :: Implementation :: PyPy',
    ],
    description='A Python library for reading and writing structured binary data.',
    license='BSD 3-Clause License',
    name='binobj',
    python_requires='>=3.4',
    packages=setuptools.find_packages(
        exclude=['docs', 'docs.*', 'tests', 'tests.*']),
    url='https://www.github.com/dargueta/binobj',
    version='0.4.0'
)
