"""Function and method decorators."""

import functools
from typing import Any
from typing import Callable
from typing import Iterable
from typing import Optional
from typing import Union

from binobj.typedefs import FieldValidator
from binobj.typedefs import StructValidator


class ValidatorMethodWrapper:
    """A wrapper around a validator method for one or more fields.

    :param callable func:
        The validator to invoke for the named fields.
    :param field_names:
        An iterable of strings; the names of the fields to be validated by
        ``func``. If ``None`` or the iterable is empty, this validator method
        should be used to validate the entire struct, not just a field.
    """

    def __init__(
        self, func: Union[FieldValidator, StructValidator], field_names: Iterable[str]
    ):
        self.func = func
        self.field_names = tuple(field_names or ())
        functools.wraps(func)(self)

    def __call__(self, *args: Any) -> Optional[bool]:
        return self.func(*args)


def validates(*field_names: str) -> Callable[[FieldValidator], ValidatorMethodWrapper]:
    """Mark a method as a validator for one or more fields.

    .. code-block:: python

        @validates('foo', 'bar')
        def validator(self, field, value):
            if value >= 10:
                raise ValidationError('%r must be in [0, 10).' % field.name,
                                      field=field)

    :param field_names:
        One or more names of fields that this validator should be activated for.

    .. warning::
        If you specify multiple validator methods, the order in which they execute
        is *not* guaranteed. If you need a specific ordering of checks, you must
        put them in the same function.

    .. note::
        Only functions and instance methods are supported. Class methods and
        static methods will cause a crash.
    """
    if not field_names:
        # Called as `@validates()`
        raise TypeError("At least one field name must be given.")
    if len(field_names) == 1 and callable(field_names[0]):
        # Common mistake -- called as `@validates` (no trailing parens)
        raise TypeError("Missing field name arguments.")
    if not all(isinstance(n, str) for n in field_names):
        raise TypeError(
            "All field names given to this decorator must be strings. Do not "
            "pass Field objects."
        )

    def decorator(func: FieldValidator) -> ValidatorMethodWrapper:
        return ValidatorMethodWrapper(func, field_names)

    return decorator


def validates_struct(func: StructValidator) -> ValidatorMethodWrapper:
    """Mark a method as a validator for the entire struct.

    The method being decorated should take a single argument aside from ``self``,
    the dict to validate. The validator is invoked right after it's been loaded,
    or right before it's dumped.

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
    return ValidatorMethodWrapper(func, ())
