"""Function and method decorators."""

from binobj import validation


def validates(*field_names):
    """A decorator that marks a method as a validator for one or more fields.

    .. note::

        If you specify multiple validators, the order in which they execute is
        *not* guaranteed. If you need a specific ordering of checks, you must
        put them in the same function.

    :param field_names:
        One or more names of fields that this validator should be activated for.
    """
    if not field_names:
        raise TypeError('At least one field name must be given.')
    elif not all(isinstance(n, str) for n in field_names):
        raise TypeError('All field names given to this decorator must be strings.'
                        'Do not pass Field objects.')

    def decorator(func):
        return validation.ValidatorMethodWrapper(func, field_names)
    return decorator


def validates_struct(func):
    """A decorator that marks a method as a validator for the entire struct."""
    return validation.ValidatorMethodWrapper(func, ())
