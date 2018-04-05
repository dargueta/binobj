"""Validation helpers for fields and structs."""


class ValidatorMethodWrapper:
    """A wrapper around a validator method for one or more fields.

    :param callable func:
        The validator to invoke for the named fields.
    :param field_names:
        A list of strings; the names of the fields to be validated by ``func``.
    """
    def __init__(self, func, field_names):
        self.func = func
        self.field_names = field_names

    def __call__(self, *args, **kwargs):
        return self.func(*args, **kwargs)


def validates(*field_names):
    """A decorator that marks a method as a validator for one or more fields.

    :param field_names:
        One or more names of fields that this validator should be activated for.
    """
    if not field_names:
        raise TypeError('At least one field name must be given.')
    elif not all(isinstance(n, str) for n in field_names):
        raise TypeError('All field names given to this decorator must be strings.'
                        'Do not pass field objects.')

    def decorator(func):
        return ValidatorMethodWrapper(func, field_names)
    return decorator
