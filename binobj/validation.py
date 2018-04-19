"""Validation helpers for fields and structs."""

import functools


class ValidatorMethodWrapper:   # pylint: disable=too-few-public-methods
    """A wrapper around a validator method for one or more fields.

    :param callable func:
        The validator to invoke for the named fields.
    :param field_names:
        An iterable of strings; the names of the fields to be validated by
        ``func``. If ``None`` or the iterable is empty, this validator method
        should be used to validate the entire struct, not just a field.
    """
    def __init__(self, func, field_names):
        self.func = func
        self.field_names = tuple(field_names or ())
        functools.wraps(func)(self)

    def __call__(self, *args, **kwargs):
        return self.func(*args, **kwargs)
