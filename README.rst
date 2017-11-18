binobj
======

A cross-platform Python 3 library for reading and writing structured binary data
in an object-oriented (ish) style.

Why use ``binobj``?
---------------

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
        signature = Const(b'BMP')
        width = UInt8()
        height = UInt8()
        pixels = Array(UInt8, count=ValueOf(width) * ValueOf(height))

    serializer = BMPFile()
    serializer.dumps({'width': 3, 'height': 2, 'pixels': [7, 8, 9, 11, 12, 13]})


``binobj`` also has other advantages in that it supports strings in any encoding
Python supports, toggling endianness on a per-field basis (necessary for ISO 9660
images), a variety of integer encodings, computed fields, validation, and more.

Note: ``ValueOf`` is currently not implemented.

System Requirements
-------------------

- This package will *not* work on a mixed-endian system. Those are pretty rare
  nowadays so chances are you won't have a problem.
- This has been tested on Python 3.3, 3.4, 3.5, 3.6, and PyPy3.5 5.8.0. (It may
  work on older versions of PyPy3.5 but I haven't tested them.) I make no
  guarantees about other implementations.

Sorry, I have no intention of supporting Python 2. Feel free to fork this and do
a backport if you like! I'd be interested to see it and even contribute.

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
For Python version management, I use `pyenv-virtualenv <https://github.com/pyenv/pyenv-virtualenv>`_.
Follow the installation instructions there, and then in the *root directory* of
this repo run:

.. code-block:: sh

    # Install all the Python versions this package supports. This will take some
    # time.
    pyenv install 3.3.6
    pyenv install 3.4.6
    pyenv install 3.5.3
    pyenv install 3.6.3
    pyenv install pypy3.5-5.8.0

    pyenv local 3.6.3 3.5.3 3.4.6 3.3.6 pypy3.5-5.8.0

    # Install dependencies you'll need for development
    pip3 install -r dev_requirements.txt

Running the Tests
~~~~~~~~~~~~~~~~~

To run the unit tests for all supported versions of Python, run ``tox``. If you
made a change to the package requirements (in ``setup.py`` or ``test_requirements.txt``)
then you'll need to rebuild the environment. Use ``tox -r`` to rebuild them and
run the tests.

License
-------

I'm releasing this under the terms of the `Three-Clause BSD License <https://tldrlegal.com/license/bsd-3-clause-license-(revised)>`_.
For the full legal text, see the ``LICENSE`` file.
