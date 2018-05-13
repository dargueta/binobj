"""Function and method decorators."""

from binobj import validation


def validates(*field_names):
    """A decorator that marks a method as a validator for one or more fields.

    :param field_names:
        One or more names of fields that this validator should be activated for.

    If you specify multiple validator methods, the order in which they execute
    is *not* guaranteed. If you need a specific ordering of checks, you must put
    them in the same function.

    Usage::

        @validates('foo', 'bar')
        def validator(self, field, value):
            if value >= 10:
                raise ValidationError('%r must be in [0, 10).' % field.name,
                                      field=field)

    .. note::

        Only functions and instance methods are supported. Class methods and
        static methods will cause a crash.
    """
    if not field_names:
        # Called as `@validates()`
        raise TypeError('At least one field name must be given.')
    elif len(field_names) == 1 and callable(field_names[0]):
        # Common mistake -- called as `@validates` (no trailing parens)
        raise TypeError('Missing field name arguments.')
    elif not all(isinstance(n, str) for n in field_names):
        raise TypeError(
            'All field names given to this decorator must be strings. Do not '
            'pass Field objects.')

    def decorator(func):    # pylint: disable=missing-docstring
        return validation.ValidatorMethodWrapper(func, field_names)
    return decorator


def validates_struct(func):
    """A decorator that marks a method as a validator for the entire struct.

    The method being decorated should take a single aside from ``self``, the
    dict to validate. The validator is invoked right after it's been loaded, or
    right before it's dumped.

    It's highly inadvisable to modify the contents, because it's easy to create
    invalid results. For example, if a struct has a field giving the length of
    the array and you change the length of that array, the length field *won't*
    update to compensate. You must do that yourself.

    Usage::

        @validates_struct
        def validator(self, struct_dict):
            if struct_dict['foo'] % 2 != 0:
                raise ValidationError("'foo' must be even", field='foo')

    .. note::

        Only functions and instance methods are supported. Class methods and
        static methods will cause a crash.
    """
    return validation.ValidatorMethodWrapper(func, ())
