Changelog
=========

0.8.0
-----

(Unreleased)

New Features
~~~~~~~~~~~~

Official support for Python 3.9.

Bugfixes
~~~~~~~~

* ``_do_load()`` could be given ``None`` for the ``loaded_fields`` argument even
  though the documentation explicitly stated that it was guaranteed to not be.
* ``_do_dump()`` would get given bytes as its ``value`` argument if the field's
  default value was ``None``.
* The ``present`` callable was sometimes passed too few arguments, potentially
  resulting in a ``TypeError``.
* Dumping an unsized iterable in an ``Array`` no longer crashes.
* Dumping a missing field whose ``default`` callable returns ``UNDEFINED`` now
  throws the expected ``MissingRequiredValueError`` exception instead of trying
  to serialize ``UNDEFINED``.
* Test on PyPy 3.6 like we claimed we were. Accidentally deleted that in the
  travis.yml file.

Breaking Changes
~~~~~~~~~~~~~~~~

* Removed ``load()``, ``loads()``, ``dump()``, and ``dumps()`` methods which were
  deprecated in 0.6.2.
* ``Array`` now skips over fields loading as ``NOT_PRESENT`` when loading.
* ``Field`` is now a generic container class, which means all subclasses must
  define their value type. *This only affects users that created their own subclasses.*

Other Changes
~~~~~~~~~~~~~

* PEP 484 type annotations have been added.
* ``Timestamp`` and its subclasses no longer inherit from ``Integer``.
* ``_NamedSentinel`` has been eliminated. In keeping with PEP 484, sentinel values
  such as ``UNDEFINED`` and ``NOT_IMPLEMENTED`` are now enums. For more information
  on why, see `Support for Singleton Types in Unions`_ in the PEP 484 documentation.
* ``from binobj.errors import *`` now only imports the exception classes.
* Travis no longer supports PyPy 3.5 so we have to stop testing on it, but the
  tests pass on CPython 3.5 and PyPy 3.6 so I think you're okay for now.

.. _Support for Singleton Types in Unions: https://www.python.org/dev/peps/pep-0484/#support-for-singleton-types-in-unions


0.7.1
-----

Released 2020-04-30

Other Changes
~~~~~~~~~~~~~

* ``__components__`` and ``__validators__`` were removed and consolidated into a
  single data structure called ``__binobj_struct__`` with a stricter and more
  logical structure. This is a purely internal change and should not affect
  most users.
* Better documentation.

0.7.0
-----

Released 2019-11-25

New Features
~~~~~~~~~~~~

* ``Array`` now sets ``size`` if it's a fixed length and its components have
  fixed sizes as well. As a consequence, ``Struct.get_size()`` now returns a
  value if all arrays inside it are sized.
* ``Nested`` also sets ``size`` if the struct it wraps is of a fixed size.
* ``Struct.from_stream()`` and ``Struct.from_bytes()`` now support an additional
  argument, ``init_kwargs``, that you can use to pass additional arguments to
  the struct's constructor. You can also use this to override a field's value.
* Struct now provides a ``repr`` that shows all of its values, e.g.

.. code-block:: python

    MyStruct(foo=123, bar="456")

Bugfixes
~~~~~~~~

Fixed URL typos in documentation.

Deprecations
~~~~~~~~~~~~

Support for Python 3.5 is deprecated. According to `3.5 release schedule`_, 3.5.9
was the last scheduled release on 2019-11-01.

.. _3.5 release schedule: https://www.python.org/dev/peps/pep-0478/

Other Changes
~~~~~~~~~~~~~

* Now testing the released Python 3.8 version instead of the development version.
* Upgraded *many* testing dependencies.

0.6.6
-----

Released 2019-11-25

Bugfixes
~~~~~~~~

For some bizarre reason package detection from the ``setup.cfg`` file stopped
working in January 2019 and every single release since 0.5.2 hasn't had the
source code in it, and the wheels have been empty. In other words, you could
install ``binobj`` but ``import binobj`` would fail!

This tweaks ``setup.py`` so that you can use it again.

0.6.5
-----

Botched release, removed from PyPI.

0.6.4
-----

Released 2019-09-01

New Features
~~~~~~~~~~~~

Add official support for PyPy 3.6.

0.6.3
-----

Released 2019-04-13

New Features
~~~~~~~~~~~~

Add official support for Python 3.8.

Other Changes
~~~~~~~~~~~~~
* Minor documentation fixes.
* Convert entire repo to use `black`_ for code formatting. I don't agree with
  all of its opinions but I do think it's better to be consistent everywhere.

.. _black: https://black.readthedocs.io/en/stable/

0.6.2
-----

Released 2019-03-05

Deprecations
~~~~~~~~~~~~

The ``load``, ``loads``, ``dump``, and ``dumps`` of ``Field`` classes are
deprecated in favor of ``from_stream``, ``from_bytes``, ``to_stream``, and
``to_bytes`` for consistency with the ``Struct`` methods.

Other Changes
~~~~~~~~~~~~~

* Minor typo fixes in the documentation.
* Changed imports in internal code to stop importing fields from ``binobj``.
* Upgraded test dependencies.

0.6.1
-----

Released: 2019-02-22

Bugfixes
~~~~~~~~

* ``Array`` used to dump all items in the iterable given to it, ignoring ``count``.
  Now it respects ``count``, and will throw an ``ArraySizeError`` if given too
  many or too few elements.
* ``Timestamp`` and subclasses treated naive timestamps as in the local timezone
  when dumping, but when ``tz_aware`` is False timestamps were loaded in UTC
  instead of being converted to the local timezone. This asymmetric behavior has
  been corrected, and naive datetimes are always local.
* ``Bytes`` would always write its ``const`` value, even if a different value
  was passed to it.
* ``Bytes`` always treated its ``size`` as if it were an integer, and never
  supported other valid things like field names or objects, even though all other
  scalar fields do.
* ``Bytes`` didn't support being unsized.
* ``Bytes`` threw an ``UnserializableValueError`` if given anything other than
  bytes or a bytearray. This was *not* in line with the other fields' behavior
  where they would "let it crash" if given an invalid type.

Other Changes
~~~~~~~~~~~~~

* Validators are no longer called when setting a field value. This would cause
  crashes when a validator depends on two fields; if one is updated, the condition
  may no longer be true, even if the user would've updated both fields before
  dumping.
* ``field_object.default`` will return ``const`` if ``const`` is defined but no
  default value was passed in. If you think about it, this makes far more sense
  than the original behavior where it returned ``UNDEFINED``.
* Added new example with CPIO archive reader.

0.6.0
-----

Released: 2019-02-16

New Features
~~~~~~~~~~~~

New field types were added:

* ``Float16``: half-precision floating-point numbers. While this has technically
  been supported since 0.4.3, it was never made explicit. ``Float16`` only works
  on Python 3.6 and above. Attempting to use it on Python 3.5 will trigger a
  ``ValueError``.
* ``Timestamp``, ``Timestamp32``, and ``Timestamp64``.

Bugfixes
~~~~~~~~

* ``Integer`` accidentally used some positional arguments instead of keyword-only.
  Only a breaking change for people who used it directly (rare) and ignored the
  "only use keyword argumets" advice.
* ``Integer`` wasn't catching ``OverflowError`` and rethrowing it as an
  ``UnserializableValueError`` like it was supposed to.
* ``helpers.iter_bytes()`` would iterate through the entire stream if ``max_bytes``
  was 0.
* ``Struct.to_dict()`` didn't omit fields marked with ``discard``.

Breaking Changes
~~~~~~~~~~~~~~~~

* Support for Python 3.4 was dropped (deprecated 0.5.1).
* Zigzag integer encoding support was dropped (deprecated 0.5.0).
* Removed the ``validation`` module and moved the decorator marker to ``decorators``.
* ``Struct.to_dict()`` now omits fields marked with ``discard``. They used to be
  left in due to a bug that has now been fixed.
* ``Float`` and ``String`` field class constructors have been changed to throw
  ``ConfigurationError`` instead of other exception types, to be more in line
  with the other fields.

Other Changes
~~~~~~~~~~~~~

* Many many fixes and clarifications to documentation.
* Changed default string encoding from Latin-1 to ISO 8859-1. They're synonyms
  for the same standard, but ISO 8859-1 is the official name. Behavior is
  identical.

0.5.2
-----

Released: 2019-01-31

Fix typo in homepage URL. Otherwise identical to 0.5.1.

0.5.1
-----

Released: 2019-01-31

This release is functionally identical to 0.5.0; changes are completely internal.

Breaking Changes
~~~~~~~~~~~~~~~~

Setuptools < 30.3.0 (8 Dec 2016) will no longer work, as configuration has been
moved to setup.cfg. Please install a newer version.

Deprecations
~~~~~~~~~~~~

Support for Python 3.4 is deprecated and will be dropped in 0.6.0. Python 3.4
reaches end-of-life in March 2019 and will no longer be maintained. See `PEP 429`_
for full details.

.. _PEP 429: https://www.python.org/dev/peps/pep-0429/

Other Changes
~~~~~~~~~~~~~

A lot of fixes for incorrect, partial, or outdated documentation.

0.5.0
-----

Released: 2018-12-21

Features
~~~~~~~~

Comparing a ``Struct`` instance to ``UNDEFINED`` is now True if and only if the
struct has all of its fields undefined. Previously a struct would never compare
equal to ``UNDEFINED``.

Deprecations
~~~~~~~~~~~~

Zigzag integer encoding support will be dropped in 0.6.0. It was an experimental
feature added when I was experimenting with different variable-length integer
formats. It's highly specific to Protobuf_ and just doesn't seem useful to have
here.

.. _Protobuf: https://developers.google.com/protocol-buffers/


Breaking Changes
~~~~~~~~~~~~~~~~

* The ``endian`` and ``signed`` keyword arguments to ``VariableLengthInteger``
  were deprecated in version 0.4.3 and have been removed.
* The ``fill_missing`` argument to ``Struct.to_dict()`` was deprecated in version
  0.4.0 and has been removed.
* ``Struct`` no longer behaves as a `MutableMapping`_. All dictionary mixin
  methods have been removed. This was deprecated in 0.4.1. Several behaviors were
  broken by this change, namely that

  * ``dict(struct_instance)`` no longer works and will cause a ``TypeError``.
    Use ``struct_instance.to_dict()``.
  * Dictionary expansion like ``**struct_instance`` will also no longer work. Use
    ``**struct_instance.to_dict()``.

.. _MutableMapping: https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping

Other Changes
~~~~~~~~~~~~~

Trivial fixes to documentation to fix broken links.

0.4.6
-----

Released: 2018-09-28

Bugfixes
~~~~~~~~

* A fair number of documentation fixes -- better explanations, formatting fixes,
  broken internal links.
* Fix bug in Makefile introduced in 0.4.4 where ``fields`` submodule wasn't
  detected as a dependency for testing and documentation building.
* Work around installation crash while testing on Python 3.4, due to a known_ race
  condition in ``setuptools``.

.. _known: https://github.com/pypa/setuptools/issues/951

Other Changes
~~~~~~~~~~~~~

* Dependencies:
  * Bump Python 3.6 testing version to 3.6.6.
  * Minimum required ``pytest`` version is now 3.1.
  * Now compatible with ``tox`` 3.x.
* Use 3.7.0 as the default version for running stuff and testing.
* Add deprecation warnings for (almost) all dictionary methods in ``Struct``.
  They've been deprecated since 0.4.1 but I didn't add the warnings.

0.4.5
-----

Released: 2018-08-04

Bugfixes
~~~~~~~~

* ``StringZ`` failed to include the trailing null when reporting its size.
* ``pylint`` was missing from the development dependencies.

Features
~~~~~~~~

Added ``present`` argument to ``Field`` that accepts a callable returning a
boolean indicating if the field is present. This is useful for optional
structures whose presence in a stream is dependent on a bit flag somewhere
earlier in the stream:

.. code-block:: python

    class MyStruct(binobj.Struct):
        flags = fields.UInt8()
        name = fields.StringZ(present=lambda f, *_: f['flags'] & 0x80)

    MyStruct.from_bytes(b'\0') == {
        'flags': 0,
        'name': fields.NOT_PRESENT,
    }

0.4.4
-----

Released: 2018-07-14

Bugfixes
~~~~~~~~

* Loading floats didn't work at all because ``size`` wasn't set in the constructor.
* Fixed minor typo in the documentation.

Other Changes
~~~~~~~~~~~~~

This release is a significant rearrangement of the code, but no behavior has
changed.

``binobj.fields`` was split from a module into a subpackage, with the following
modules:

* ``base``: The ``Field`` base class and a few other things.
* ``containers``: The fields used to nest other schemas and fields, such as
  ``Array`` and ``Nested``.
* ``numeric``: All fields representing numeric values, such as integers and
   floats.
* ``stringlike``: All fields that are text strings or bytes.


0.4.3
-----

Released: 2018-07-09

Bugfixes
~~~~~~~~

* You no longer need to specify the signedness of variable-length integer fields,
  since those are hard-coded by the standards anyway.
* Outdated documentation was missing some arguments in ``_do_load`` and ``_do_dump``
  examples.

Features
~~~~~~~~

* Added the ``Float32`` and ``Float64`` fields. These support 32- and 64-bit
  floating-point numbers stored in IEEE-754:2008 interchange format.
* Added support for signed and unsigned `LEB128 <https://en.wikipedia.org/wiki/LEB128>`_
  variable-length integers.

Deprecations
~~~~~~~~~~~~

* Passing the ``signed`` or ``endian`` keyword arguments to a ``VariableLengthInteger``
  is now superfluous, and will cause a ``DeprecationWarning``. These arguments
  will be removed in a future version.
* Importing ``Field`` objects *directly* from ``binobj`` is deprecated. Import
  them from ``binobj.fields`` instead. This will reduce namespace clutter.

.. code-block:: python

    # Deprecated:
    from binobj import String

    # Do this instead:
    from binobj.fields import String

Other Changes
~~~~~~~~~~~~~

* Use the "Alabaster" theme for documentation instead of RTD.
* Relax the dependency on ``bumpversion``.

0.4.2
-----

Released: 2018-06-07

Bugfixes
~~~~~~~~

Variable-length integer fields now set their ``size`` attribute if ``const`` is
defined. *Not* doing so was apparently a deliberate decision, which I no longer
understand.

Other Changes
~~~~~~~~~~~~~

* ``Union`` now throws a ``ConfigurationError`` if it gets a ``Field`` class
  instead of an instance of a ``Field`` class. This would otherwise result in
  hard to debug ``TypeError``\s being thrown when trying to load or dump.
* Trying to use a ``computes`` decorator on a const field will trigger a
  ``ConfigurationError``.
* ``Bytes`` no longer crashes with an ``UndefinedSizeError`` if it isn't given a
  size. I'm not sure why I ever thought that ``Bytes`` should only be a fixed
  length.

0.4.1
-----

Released: 2018-05-13

Bugfixes
~~~~~~~~

* Struct size couldn't be calculated if the struct contained computed fields or
  had to use the default value for any field.
* Setting the value of a computed or const field would persist until that field
  was deleted. Trying to modify a computed or const field will now trigger a
  ``ImmutableFieldError``.
* Accessing a field as an attribute no longer sets the field to its default
  value if the field hasn't been assigned yet. This made sense before computed
  fields were added, since ostensibly changing one field wouldn't affect any
  others.
* Values assigned to a struct using dictionary notation were not validated.
* ``len()`` now throws a ``MissingRequiredValueError`` exception if the struct
  size couldn't be computed. ``UndefinedSizeError`` is a configuration error and
  in retrospect made no sense to throw there.
* A better error message is shown when accessing a ``Struct`` using a field name
  that doesn't exist.
* Attempting to get the value of a field that hasn't been set yet via dictionary
  access used to throw a ``KeyError`` even if it was a computed field. Now it
  throws the expected ``MissingRequiredValueError``.

Other Changes
~~~~~~~~~~~~~

* Dictionary methods on ``Struct`` like ``get``, ``setdefault``, etc. are
  **deprecated** and should not be used anymore. They will be removed in 0.5.0.
* Validator decorators now detect when they're being misused (i.e. called as
  ``@validator`` instead of ``@validator()`` and throw a helpful exception.
* Bump tested CPython versions to the latest release, i.e. 3.4.7 -> 3.4.8, etc.
* Bump PyPy3.5 5.10 to v6.0


0.4.0
-----

Released: 2018-04-21

Bugfixes
~~~~~~~~

* Removed unused ``__computed_fields__`` property from ``Struct`` classes. It was
  accidentally left in.
* Fixed WAV file generation in the examples. It was writing the frequency of the
  wave to the file, not the amplitude.
* Miscellaneous tweaks and typo corrections in documentation.

Features
~~~~~~~~

Added support for adding validators on fields, both as methods in their ``Struct``
and passed in to the constructor. You can also have validator methods that
validate the entire ``Struct`` just after loading or just before dumping.

Breaking Changes
~~~~~~~~~~~~~~~~

* Dropped support for Python 3.3, which has been deprecated. Please upgrade to a
  newer version of Python.
* ``VariableSizedFieldError`` was deprecated in 0.3.1. It has been removed and
  completely replaced by ``UndefinedSizeError``.

Other Changes
~~~~~~~~~~~~~

* Start testing on Python 3.7.
* Assigning directly to the ``__values__`` dict in a ``Struct`` is **deprecated**,
  as it circumvents validators. ``__values__`` will be removed in a future
  release.

0.3.1
-----

Released: 2018-03-28

Bugfixes
~~~~~~~~

* Fixed bug where ``Bytes`` wasn't checking how many bytes it was writing when
  dumping.
* Fixed bug where ``Field.size`` was incorrectly computed for fields where
  ``len(const)`` wasn't equivalent to the field size, e.g. for ``String`` fields
  using a UTF-16 encoding.


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
