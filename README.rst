binobj
======

|build-status| |python-versions| |installs-month| |installs-ever|

.. |build-status| image:: https://travis-ci.org/dargueta/binobj.svg?branch=master
   :alt: Build status
   :target: https://travis-ci.org/dargueta/binobj

.. |python-versions| image:: https://img.shields.io/badge/python-3.5,%203.6,%203.7,%203.8,%203.9-blue.svg
   :alt: Python versions

.. |installs-month| image:: https://pepy.tech/badge/binobj/month
   :alt: Installs per month
   :target: https://pepy.tech/project/binobj

.. |installs-ever| image:: https://pepy.tech/badge/binobj
   :alt: Total installs
   :target: https://pepy.tech/project/binobj

A cross-platform Python 3 library for reading and writing structured binary data
in an object-oriented (ish) style.

Why use ``binobj``?
-------------------

You may have used Python's built-in ``struct`` library to load and dump binary
data. It's unwieldy for larger or more complex data structures, and the format
strings are easy to get wrong. ``binobj`` is different in that it takes a class-based
approach to declaring binary structures.

Take a look at this example using ``struct``:

.. code-block:: python

    data = (b'BM', 1024, 0, 12, 40, 32, 32, 1, 1, 0, 0, 72, 72, 2, 2)
    header_bytes = struct.pack('<2sIIIIiiHHIIiiII', *data)
    loaded = struct.unpack('<2sIIIIiiHHIIiiII', header_bytes)
    n_pixels = loaded[5] * loaded[6]


The same example rewritten using ``binobj``:

.. code-block:: python

    class BMP(binobj.Struct):
        magic = binobj.Bytes(const=b'BM')
        file_size = binobj.UInt32()
        _reserved = binobj.Bytes(const=b'\0\0\0\0', discard=True)
        pixels_offset = binobj.UInt32()

        # Legacy DIB header
        header_size = binobj.UInt32(const=40)
        image_width = binobj.Int32()
        image_height = binobj.Int32()
        n_color_planes = binobj.UInt16()
        n_bits_per_pixel = binobj.UInt16()
        compression_method = binobj.UInt32(default=0)
        bitmap_size = binobj.UInt32()
        v_resolution = binobj.Int32()
        h_resolution = binobj.Int32()
        n_palette_colors = binobj.UInt32()
        n_important_colors = binobj.UInt32()

    bmp = BMP(file_size=1024, pixels_offset=12, image_width=32, image_height=32, ...)
    header_bytes = bytes(bmp)
    loaded = BMP.from_bytes(header_bytes)
    n_pixels = loaded.image_width * loaded.image_height


``binobj`` also has other advantages in that it supports strings in any encoding
Python supports, toggling endianness on a per-field basis (necessary for ISO 9660
images), a variety of integer encodings, computed fields, validation, and more.

System Requirements
-------------------

- This package will *not* work on a `mixed-endian`_ system. Those are pretty rare
  nowadays so chances are you won't have a problem.
- This has been tested on Python 3.5-3.8, PyPy3.5, and PyPy3.6.

Sorry, I have no intention of supporting Python 2. Feel free to fork this and do
a backport if you like! I'd be interested to see it and might even contribute.

.. _mixed-endian: https://en.wikipedia.org/wiki/Endianness#Mixed

Installation
------------

You can install this with ``pip`` like so:

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

I'm releasing this under the terms of the `3-Clause BSD License`_. For the full
legal text, see ``LICENSE.txt`` in the repository.

.. _3-Clause BSD License: https://tldrlegal.com/license/bsd-3-clause-license-(revised)
