"""Helpful decorators for adding functionality.

.. versionadded:: 0.3.0
"""

from binobj import errors


def computes(field):
    """Decorator that marks a function as computing the value for a field.

    You can use this for automatically assigning values based on other fields.
    For example, suppose we have this struct::

        class MyStruct(Struct):
            n_numbers = UInt8()
            numbers = Array(UInt8(), count=n_numbers)

    This works great for loading, but when we're dumping we have to pass in a
    value for ``n_numbers`` explicitly. We can use the ``computes`` decorator
    to relieve us of that burden::

        class MyStruct(Struct):
            n_numbers = UInt8()
            numbers = Array(UInt8(), count=n_numbers)

            @computes(n_numbers)
            def _assign_n_numbers(self, all_fields):
                return len(all_fields['numbers'])

    Some usage notes:

    * The computing function will *not* be called if a value is explicitly set
      for the field by the calling code.
    * Computed fields are executed in the order that the fields are dumped, so
      a computed field must *not* rely on the value of another computed field
      occurring after it.

    .. versionadded:: 0.3.0
    """
    if not isinstance(field, str):
        field = field.name

    def decorator(method):
        # Expect a Struct method as the argument for this decorator.
        if not hasattr(method, '__self__'):
            raise TypeError('Decorator requires instance method.')
        elif field in method.__self__.__computed_fields__:
            raise errors.ConfigurationError(
                "Cannot define two computing functions for field %r." % field,
                field=field)

        method.__self__.__computed_fields__[field] = method
        return method

    return decorator
