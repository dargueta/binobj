binobj
======

|build-status| |python-versions|

.. |build-status| image:: https://travis-ci.org/dargueta/binobj.svg?branch=master
   :alt: Build status
   :target: https://travis-ci.org/dargueta/binobj

.. |python-versions| image:: https://img.shields.io/badge/python-3.3,%203.4,%203.5,%203.6-blue.svg
   :alt: Python versions

A cross-platform Python 3 library for reading and writing structured binary data
in an object-oriented (ish) style.

Why use ``binobj``?
-------------------

You may have seen other libraries like `Construct <https://github.com/construct/construct>`_
that accomplish the same job. ``binobj`` is different in that it's heavily inspired
by `Marshmallow <http://marshmallow.readthedocs.io/en/latest/>`_ and takes a
more class-based approach to declaring binary structures.

Take a look at this example taken from the README of ``construct`` library:

.. code-block:: python

    format = Struct(
        "signature" / Const(b"BMP"),
        "width" / Int8ub,
        "height" / Int8ub,
        "pixels" / Array(this.width * this.height, Byte),
    )

    format.build(dict(width=3,height=2,pixels=[7,8,9,11,12,13]))


The same example rewritten using ``binobj``:

.. code-block:: python

    class BMPFile(Struct):
        signature = Bytes(const=b'BMP')
        width = UInt8()
        height = UInt8()
        pixels = Array(UInt8(), count=width * height)

    bmp_file = BMPFile(width=3, height=2, pixels=[7,8,9,11,12,13])
    bytes(bmp_file)


``binobj`` also has other advantages in that it supports strings in any encoding
Python supports, toggling endianness on a per-field basis (necessary for ISO 9660
images), a variety of integer encodings, computed fields, validation, and more.

Note: Size expressions are currently not implemented but they're in the works.

System Requirements
-------------------

- This package will *not* work on a mixed-endian system. Those are pretty rare
  nowadays so chances are you won't have a problem.
- This has been tested on Python 3.3, 3.4, 3.5, 3.6, and PyPy3.5.

Sorry, I have no intention of supporting Python 2. Feel free to fork this and do
a backport if you like! I'd be interested to see it and might even contribute.

Installation
------------

Once I get this up on PyPI, you can install it with ``pip`` like so:

.. code-block:: sh

    pip3 install binobj

- Be sure to use ``pip3`` and not ``pip``, because ``pip`` defaults to Python 2.
- If you get a "Permission Denied" error, try:

.. code-block:: sh

    pip3 install --user binobj

Side note: Don't use ``sudo`` (even ``sudo -EH``) to force a package to install,
as that's a security risk. See `this answer <https://stackoverflow.com/a/42021993>`_
on Stack Overflow to find out why.

Testing and Development
-----------------------

This package uses `Tox <https://tox.readthedocs.io/en/latest/>`_ to run tests on
multiple versions of Python.

Setup
~~~~~

To set up your development environment, you'll need to install a few things.

* For Python version management, I use `pyenv-virtualenv <https://github.com/pyenv/pyenv-virtualenv>`_.
  Follow the installation instructions there.
* You'll also need ``make``. Depending on your platform you can install it in
  one of several ways:

  * macOS: ``brew install make``
  * Debian systems (e.g. Ubuntu): ``sudo apt-get install make``
  * Windows: Use `Cygwin <https://www.cygwin.com/>`_ and install it during setup.

Once you have those installed, in the root directory of this repo run:

.. code-block:: sh

    make setup

Running the Tests
~~~~~~~~~~~~~~~~~

To run the unit tests for all supported versions of Python, run ``make test``.
The environments will automatically be rebuilt if needed.

Issues and Feature Requests
~~~~~~~~~~~~~~~~~~~~~~~~~~~

To report an issue, request a feature, or propose a change, please file a
report on the project's GitHub page `here <https://github.com/dargueta/binobj/issues>`_.

License
-------

I'm releasing this under the terms of the `Three-Clause BSD License <https://tldrlegal.com/license/bsd-3-clause-license-(revised)>`_.
For the full legal text, see `LICENSE.txt <./LICENSE.txt>`_.
