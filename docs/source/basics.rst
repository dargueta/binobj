Tutorial: The Basics
--------------------

``binobj`` allows you to create classes to declare the structure of binary files
or streams in a convenient object-oriented way. It supports a variety of field
types, and if you need something a bit more specialized you can always subclass
:class:`~binobj.fields.Field` or one of its subclasses to create the functionality
you need.

Plain Old Strings
~~~~~~~~~~~~~~~~~

Suppose you want to create an address book application in Python, and want to
store people's information in a file. Each person has a first name, a last name,
and a phone number. You could do something like:

.. code-block:: python

    import binobj
    from binobj import fields

    class PersonInfo(binobj.Struct):
        first_name = fields.String(size=8)
        last_name = fields.String(size=8)
        phone = fields.String(size=12)      # Assuming a US phone number

A little explanation: ``PersonInfo`` is a structure with first name and last
name ASCII strings that must be exactly eight bytes each, and a phone number that
must be exactly twelve digits. Not too flexible, but we're just getting started.

Let's save a contact to a file.

.. code-block:: python

    person = PersonInfo(first_name='James', last_name='Kirk', phone='817-555-9121')

    # **Always* open files in binary mode!
    with open('contacts.dat', 'wb') as fdesc:
        person.to_stream(fdesc)

Unfortunately this will instantly crash::

    binobj.errors.ValueSizeError: String(name='first_name') can't serialize value: Value doesn't fit into 8 bytes.

This is because ``James`` is only five bytes long. Hm. We could pad the strings
with trailing spaces and remove the trailing spaces when loading a record. Let's
try that.


.. code-block:: python

    person = PersonInfo(first_name='James   ', last_name='Kirk    ',
                        phone='817-555-9121')

    with open('contacts.dat', 'wb') as fdesc:
        person.to_stream(fdesc)

That worked! Let's read the record back.

.. code-block:: python

    with open('contacts.dat', 'rb') as fdesc:
        person = PersonInfo.from_stream(fdesc)

    assert person.first_name == 'James   '
    assert person.last_name == 'Kirk    '

Looks like we got our data back correctly.

Text and Encodings
~~~~~~~~~~~~~~~~~~

``binobj`` allows you to specify the character encoding of strings individually.
Suppose you want to internationalize your app and make it handle names with
accents in them, or even in other writing systems. We can change the strings to
be UTF-8:

.. code-block:: python

    class PersonInfo(binobj.Struct):
        first_name = fields.String(size=8, encoding='utf-8')
        last_name = fields.String(size=8, encoding='utf-8')
        phone = fields.String(size=12)

    person = PersonInfo(first_name='Renée  ', last_name='Duchamps',
                        phone='123-456-7890')

    assert bytes(person) == b'Ren\xc3\xa9e  Duchamps123-456-7890'

.. note::

    Be careful with multibyte encodings! The ``size`` argument specifies the size
    of the field in *bytes*, not *characters*!


Variable-Length Fields
~~~~~~~~~~~~~~~~~~~~~~

It can get a bit tedious to remember to pad strings with spaces just so we can
save the file without errors. Also: what happens if you need to store info for
someone with a long last name like O'Shaughnessy or Ramachandran? We could use a
variable-length string, like :class:`~binobj.fields.StringZ`. This stores a
string with a null byte to signal the end, like in C.

.. code-block:: python

    class PersonInfo(binobj.Struct):
        first_name = fields.StringZ(encoding='utf-8')
        last_name = fields.StringZ(encoding='utf-8')
        phone = fields.StringZ()    # Allow international phone numbers!


    with open('contacts.dat', 'wb+') as fdesc:
        person = PersonInfo(first_name='Benjamin', last_name='Sisko',
                            phone='415-555-8570')
        person.to_stream(fdesc)

        # You can reuse structs if you like, they're mutable.
        person.first_name = 'James'
        person.last_name = 'Kirk'
        person.phone = '817-555-9121'
        person.to_stream(fdesc)

Arrays
~~~~~~

Let's add a new feature to allow people to have two phone numbers. You can use
an :class:`~binobj.fields.Array` for this.


.. code-block:: python

    class PersonInfo(binobj.Struct):
        first_name = fields.StringZ(encoding='utf-8')
        last_name = fields.StringZ(encoding='utf-8')
        phone_numbers = fields.Array(fields.StringZ(), count=2)

    person = PersonInfo(first_name='Nerys', last_name='Kira')
    person.phone_numbers = ['842-194-1959', '842-138-1877']

    assert person.to_bytes() == b'Nerys\0Kira\0842-194-1959\0842-138-1877\0'

    loaded = PersonInfo.from_bytes(b'Nerys\0Kira\0842-194-1959\0842-138-1877\0')

    assert person == loaded

Great! But what if someone only has one phone number, or (gasp) *no* phone
numbers? Don't worry, arrays can be of variable size. You'll need to provide a
function to tell ``binobj`` when the array ends. In this example, we'll use an
empty phone number to signal the end of the array.

.. code-block:: python

    def should_halt(array, stream, values, context, loaded_fields):
        if values and values[-1] == '':
            # Don't forget to remove the empty phone number that we use as a
            # signal to stop.
            del values[-1]
            return True
        return False


    class PersonInfo(binobj.Struct):
        first_name = fields.StringZ(encoding='utf-8')
        last_name = fields.StringZ(encoding='utf-8')
        phone_numbers = fields.Array(fields.StringZ(), halt_check=should_halt)

    data = b'Julian\0Bashir\x00173-994-0982\0\0'
    person = PersonInfo.from_bytes(data)

    assert person == {
        'first_name': 'Julian',
        'last_name': 'Bashir',
        'phone_numbers': ['173-994-0982']
    }

.. note::

    If you're using some sort of sentinel value to indicate the end of an array,
    it's up to you to add it *before* serializing your struct. ``binobj`` doesn't
    know how to do that for you (yet).

Nested Structs
~~~~~~~~~~~~~~

Let's kick this up a notch and add support for addresses. You could store an
address as a single string, which is fine, but what if we want to make it a bit
more structured than that? Fortunately, we can nest a :class:`~binobj.structures.Struct`
inside another.

.. code-block:: python

    class USAddress(binobj.Struct):
        line_1 = fields.StringZ()
        line_2 = fields.StringZ(default='')     # Don't make line 2 required
        city = fields.StringZ()
        state = fields.String(size=2)
        zip_code = fields.String(size=5)

    class PersonInfo(binobj.Struct):
        first_name = fields.StringZ(encoding='utf-8')
        last_name = fields.StringZ(encoding='utf-8')
        phone_numbers = fields.Array(fields.StringZ(), halt_check=should_halt)

        # Important: You must pass in your nested struct's *class*, not an
        # instance of the class!
        address = fields.Nested(USAddress)

    addr = USAddress(line_1='123 Main Street', city='Anytown', state='CA',
                     zip_code='94199')
    person = PersonInfo(first_name='Jadzia', last_name='Dax', phone_numbers=[''],
                        address=addr)

    assert bytes(person) == b'Jadzia\x00Dax\x00\x00123 Main Street\x00\x00Anytown\x00CA94199'

    loaded = PersonInfo.from_bytes(bytes(person))
    assert loaded == person

Arrays of Structs
~~~~~~~~~~~~~~~~~

Can you make arrays of nested structs? Absolutely! We can take advantage of that
to support multiple addresses for a single person. We'll indicate the number of
addresses a person has using an integer field.

As of version 0.3.0 you can use a :class:`~binobj.fields.Field` as the array size,
so instead of creating a halting function like we did with ``phone_numbers``, we
can pass ``n_addresses`` as the value for ``count``:

.. code-block:: python

    # USAddress stays the same

    class PersonInfo(binobj.Struct):
        first_name = fields.StringZ(encoding='utf-8')
        last_name = fields.StringZ(encoding='utf-8')
        phone_numbers = fields.Array(fields.StringZ(), halt_check=should_halt)
        n_addresses = fields.UInt8()    # 0-255 addresses
        addresses = fields.Array(fields.Nested(USAddress), count=n_addresses)

    # Now let's write it to a file.
    addresses = USAddress(line_1='123 Main Street', city='Anytown', state='CA',
                          zip_code='94199')
    person = PersonInfo(first_name='Jadzia', last_name='Dax', phone_numbers=[''],
                        n_addresses=1, addresses=[addr])

    assert bytes(person) == b'Jadzia\x00Dax\x00\x00\x01123 Main Street\x00\x00Anytown\x00CA94199'

    loaded = PersonInfo.from_bytes(bytes(person))
    assert loaded == person


Creating Custom Fields
~~~~~~~~~~~~~~~~~~~~~~

Suppose we want to give users the ability to record someone's birthday. ``binobj``
doesn't have a ``Date`` type, so we're going to have to roll our own. There's a
number of ways we can represent a date but the easiest way seems to be to record
the date as a string in ``YYYYMMDD`` format.

When you're creating your own field, there are only two methods you must implement
yourself: ``_do_load`` and ``_do_dump``.

Always keep in mind: The ``stream`` argument to these methods is always a binary
stream that reads and writes :class:`bytes`, so be sure to encode and decode
your strings accordingly.

.. code-block:: python

    import datetime

    class Date(binobj.Field):
        def _do_load(self, stream, context):
            """Load a date from the stream."""
            date_bytes = stream.read(8)
            date_string = date_bytes.decode('ascii')

            timestamp = datetime.datetime.strptime(date_string, '%Y%m%d')
            return timestamp.date()

        def _do_dump(self, stream, data, context):
            """Dump a date into the stream."""
            # Let the user pass in a date or datetime
            if isinstance(data, datetime.datetime):
                data = data.date()

            date_string = data.strftime('%Y%m%d')
            stream.write(date_string.encode('ascii'))

Putting It All Together
~~~~~~~~~~~~~~~~~~~~~~~

Let's look at the final version of our file:

.. code-block:: python

    import datetime

    import binobj
    from binobj import fields


    class Date(binobj.Field):
        def _do_load(self, stream, context, loaded_fields):
            """Load a date from the stream."""
            date_bytes = stream.read(8)
            date_string = date_bytes.decode('ascii')

            timestamp = datetime.datetime.strptime(date_string, '%Y%m%d')
            return timestamp.date()

        def _do_dump(self, stream, data, context, all_fields):
            """Dump a date into the stream."""
            # Let the user pass in a date or datetime
            if isinstance(data, datetime.datetime):
                data = data.date()

            date_string = data.strftime('%Y%m%d')
            stream.write(date_string.encode('ascii'))


    class USAddress(binobj.Struct):
        line_1 = fields.StringZ()
        line_2 = fields.StringZ(default='')
        city = fields.StringZ()
        state = fields.String(size=2)
        zip_code = fields.String(size=5)


    def should_halt_phones(array, stream, values, context, loaded_fields):
        if values and values[-1] == '':
            del values[-1]
            return True
        return False

    def should_halt_addrs(array, stream, values, context, loaded_fields):
        return len(values) >= loaded_fields['n_addresses']


    class PersonInfo(binobj.Struct):
        first_name = fields.StringZ(encoding='utf-8')
        last_name = fields.StringZ(encoding='utf-8')
        birthday = Date()
        phone_numbers = fields.Array(fields.StringZ(),
                                     halt_check=should_halt_phones)
        n_addresses = fields.UInt8()
        addresses = fields.Array(fields.Nested(USAddress),
                                 halt_check=should_halt_addrs)

    addr_1 = USAddress(line_1='123 Main Street', line_2='Apt #104', city='Anytown',
                       state='TX', zip_code='75710')
    addr_2 = USAddress(line_1='456 22nd Street', city='Townsville', state='IL',
                       zip_code='60184')
    person = PersonInfo(
        first_name='Miles',
        last_name="O'Brien",
        birthday=datetime.date(2205, 10, 15),
        phone_numbers=['586-188-1958', '586-002-0611', ''],
        n_addresses=2,
        addresses=[addr_1, addr_2])

    assert bytes(person) == b"Miles\x00O'Brien\x0022051015586-188-1958\x00" \
                            b"586-002-0611\x00\x00\x02123 Main Street\x00" \
                            b"Apt #104\x00Anytown\x00TX75710456 22nd Street\x00" \
                            b"\x00Townsville\x00IL60184"

    loaded = PersonInfo.from_bytes(bytes(person))

    # We need to append the sentinel value to the phone numbers because it gets
    # stripped out when loading, but we had to put it in manually in ``person``.
    loaded.phone_numbers.append('')
    assert loaded == person


Pretty cool, huh? There's loads more you can do. Check out the ``full_examples``
directory in the tests for more real-world examples of what you can do. The
documentation in :mod:`~binobj.fields` and :mod:`binobj.structures` might also
be of interest to you.
