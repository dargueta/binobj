Changelog
=========

0.3.1
-----

Released: 2018-XX-XX

Bugfixes
~~~~~~~~

* Fixed bug where ``Bytes`` wasn't checking how many bytes it was writing when
  dumping.


Other Changes
~~~~~~~~~~~~~

* ``VariableSizedFieldError`` has been **deprecated**, and will be replaced by
  ``UndefinedSizeError``. This is because the exception name and error message
  was misleadingly narrow in scope.
* Removed undocumented ``loaded_fields`` and ``all_fields`` arguments from the
  loading and dumping methods in ``Struct``. They were left in by mistake and
  never used.


0.3.0
-----

Released: 2018-03-23

Bugfixes
~~~~~~~~

* Fixed field redefinition detection. Subclassing wasn't supported in earlier
  versions but the code was still there.

Features
~~~~~~~~

1. ``Array`` can now take another ``Field`` or a string naming a ``Field`` as its
   ``count`` argument. This lets you avoid having to write a halting function:

.. code-block:: python

    # As of 0.3.0:
    class MyStruct(Struct):
        n_numbers = UInt16()
        numbers = Array(UInt16(), count=n_numbers)

    # For earlier versions:

    def halt_n_numbers(seq, stream, values, context, loaded_fields):
        return len(values) >= loaded_fields['n_numbers']

    class MyStruct(Struct):
        n_numbers = UInt16()
        numbers = Array(UInt16(), halt_check=halt_n_numbers)

2. The new ``computes`` decorator gives you the ability to use a function to
   dynamically compute the value of a field when serializing, instead of passing
   it in yourself.

3. New field type ``Union`` allows you to emulate C's ``union`` storage class
   using fields, structs, or any combination of the two.

4. Added ``struct`` and ``obj`` keyword arguments to ``ConfigurationError`` to
   give more flexibility in what errors it and its subclasses can be used for.


Breaking Changes
~~~~~~~~~~~~~~~~

None.


Documentation
~~~~~~~~~~~~~

* Changed development stage from alpha stage to beta.
* Expanded documentation of existing code, fixed inter-module references.


0.2.1
-----

Released: 2018-03-18


Bugfixes
~~~~~~~~

1. Fixed argument names in overridden methods of some fields differing from their
   superclass' signature. Affects ``Integer``, ``String``, ``StringZ`` and
   ``VariableLengthInteger``.
2. Fixed ``to_dict()`` method of ``Struct`` so that it recurses and converts all
   nested fields and arrays into Python dicts as well. This means that the output
   of ``Struct.to_dict()`` is JSON-serializable if all fields are defined.
3. Changed ``BytesIO`` in documentation to ``BufferedIOBase`` since ``FileIO`` is
   also a legitimate input type.
4. ``Array`` halt functions can now reference the fields that have already been
   deserialized. This was supposed to be included in 0.1.0 but somehow was
   overlooked.

Breaking Changes
~~~~~~~~~~~~~~~~

* The fix for bug 2:

  * ``dict(struct)`` and ``struct.to_dict()`` no longer give identical results.
  * For nested structures, ``struct.to_dict()`` will return dictionaries where
    the old behavior would return instances of those ``Struct`` objects. This
    only matters if your code relied on nested structs being ``Struct`` objects.

* The fix for bug 4 added additional a positional argument to ``_do_load``,
  ``_do_dump``, and the halt functions. This will break subclasses that define
  these functions, but the fix is minimal:

  * Add ``loaded_fields`` as the last argument to your halt functions as well as
    any overridden ``_do_load`` methods in custom fields.
  * Add ``all_fields`` as the last argument to ``_do_dump`` methods in custom
    fields.


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

Breaking Changes
~~~~~~~~~~~~~~~~

None.


0.1.0
-----

Released: 2018-03-03

Initial release.
