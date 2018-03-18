Changelog
=========


0.2.1
-----

Released: 2018-XX-XX

Bugfixes
~~~~~~~~

* Changed ``BytesIO`` in documentation to ``BufferedIOBase`` since ``FileIO`` is
  also a legitimate input type.

Documentation
~~~~~~~~~~~~~

* Added WAV file example and unit tests.
* Changed "end to end tests" file into a BMP file example since it was only using
  the BMP format anyway.
* Added comprehensive tutorial on basics with a bit of intermediate stuff.


0.2.0
-----

Released: 2018-03-04

Bugfixes
~~~~~~~~

* ``StringZ`` can now load strings in character encodings that use more than one
  byte to represent null, e.g. UTF-16.
* Fixed some typos in documentation.

Features
~~~~~~~~

* ``String`` and its subclasses now take a ``pad_byte`` argument that pads strings
  with that byte if they're too short after encoding. For example:

.. code-block:: python

    >>> String(size=4, pad_byte=b' ').dumps('a')
    b'a   '


0.1.0
-----

Released: 2018-03-03

Initial release.
