import setuptools
import sys

# Thwart installation for unsupported versions of Python. `pip` didn't start
# enforcing `python_requires` until 9.0.
if sys.version_info < (3, 3):
    raise RuntimeError('Unsupported Python version: ' + sys.version)


setuptools.setup(
    author='Diego Argueta',
    author_email='dargueta@users.noreply.github.com',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: Implementation :: CPython',
        'Programming Language :: Python :: Implementation :: PyPy',
    ],
    description='A Python library for reading and writing structured binary data.',
    install_requires=[
        'enum34>=1.0; python_version<"3.4"',
    ],
    license='BSD 3-Clause License',
    name='binobj',
    python_requires='>=3.3',
    packages=setuptools.find_packages(
        exclude=['docs', 'docs.*', 'tests', 'tests.*']),
    url='https://www.github.com/dargueta/binobj',
    version='0.2.1'
)
