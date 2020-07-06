"""Function and method decorators."""

import functools
import typing
from typing import Any
from typing import Callable
from typing import Iterable
from typing import Optional
from typing import Type
from typing import TypeVar
from typing import Union

import attr
import typing_extensions

from binobj import errors
from binobj import fields
from binobj.typedefs import FieldValidator
from binobj.typedefs import StructValidator


if typing.TYPE_CHECKING:
    from binobj.structures import Struct


TStruct = TypeVar("TStruct", bound="Struct")


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

    def __call__(self, *args: Any, **kwargs: Any) -> Optional[bool]:
        return self.func(*args, **kwargs)  # type: ignore


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


@attr.s
class AnnotationInfo:
    name = attr.ib(type=str)
    type_class = attr.ib(type)
    type_args = attr.ib(type=tuple, default=())
    has_default = attr.ib(type=bool, default=None)
    default_value = attr.ib(type=Any, default=fields.UNDEFINED)
    nullable = attr.ib(type=bool, default=False)

    @classmethod
    def from_annotation(
        cls, field_name: Any, annotation: Any, struct_class: Type[TStruct]
    ) -> "AnnotationInfo":
        type_class = typing_extensions.get_origin(annotation)
        type_args = typing_extensions.get_args(annotation)
        nullable = type(None) in type_args

        # Handle Optional[T] which gets rendered as Union[T, type(None)].
        # We have to compare types directly with `is` because the type annotations don't
        # support isinstance() and issubclass().
        if type_class is Union:
            # Filter out None from the type arguments. Again, we have to use `is`. :(
            type_args = tuple(t for t in type_args if t is not type(None))

            if len(type_args) == 1:
                # The type annotation was Optional[T]. Pretend the annotation was T, and
                # resolve *its* arguments just in case T is of the form X[Y, ...].
                type_class = type_args[0]
                type_args = typing_extensions.get_args(type_class)
            else:
                # If we get here then the type annotation for this field is a Union with
                # two or more types. This means the caller is probably attempting to
                # declare a `binobj.fields.Union`.
                raise errors.InvalidTypeAnnotationError(
                    field=field_name, annotation=annotation
                )

        return cls(
            name=field_name,
            type_class=type_class,
            type_args=type_args,
            has_default=hasattr(struct_class, field_name),
            default_value=getattr(struct_class, field_name, fields.UNDEFINED),
            nullable=nullable,
        )


def dataclass(class_object: Type[TStruct]) -> Callable[[], Type[TStruct]]:
    """Mark a Struct as using `PEP 526`_ declarations for its fields.

    If you use this decorator, *all* fields must be declared with PEP 526 annotations.
    You can't mix this system with the original assignment-based one.

    Here are a few examples of how you can declare your fields::

        class MyStruct(binobj.Struct):
            # Preferred: use a class object
            foo: UInt16

            # You can define default values like this
            bar: StringZ = ""

            # You can pass struct classes -- no need for a `Nested` wrapper. Forward
            # references using strings are *not* supported.
            sub_struct: MyOtherStruct

            # Instances are allowed but are less readable. Be careful not to *assign*
            # the field instance!
            baz: Timestamp64(signed=False)

            # You can pass functions for default values just as if you were calling the
            # constructor, but this looks confusing and is **not recommended**. This may
            # throw an exception in the future if I decide it's too egregious.
            bam: StringZ = lambda: os.sep

    .. versionadded:: 0.9.0

    .. _PEP 526: https://www.python.org/dev/peps/pep-0526/
    """
    meta = class_object.__binobj_struct__
    if meta.num_own_fields > 0:
        raise errors.MixedDeclarationsError(struct=class_object)

    field_index = 0
    n_fields_found = 0
    byte_offset = meta.size_bytes
    all_annotations = typing.get_type_hints(class_object)

    for name, raw_annotation in all_annotations.items():
        annotation = AnnotationInfo.from_annotation(
            field_name=name, annotation=raw_annotation, struct_class=class_object
        )
        if isinstance(annotation.type_class, type):
            # We got a class object. Could be a struct or field, ignore everything else.
            if issubclass(annotation.type_class, Struct):
                # A Struct class is shorthand for Nested(Struct).
                field_instance = fields.Nested(annotation.type_class)
            elif issubclass(annotation.type_class, fields.Field):
                # This is a Field class. Initialize it with no arguments aside from its
                # default value, if provided. This gives us a Field instance.
                field_instance = annotation.type_class(default=annotation.default_value)
            else:
                # Not a struct or field class -- ignore
                continue
        elif not isinstance(annotation.type_class, fields.Field):
            # Not an instance of Field -- ignore
            continue
        else:
            # Else: The annotation is a field instance. Atypical but we'll allow it.
            field_instance = annotation.type_class

        if name in meta.components:
            # Puke -- the field was already defined in the superclass.
            raise errors.FieldRedefinedError(struct=class_object.__name__, field=name)

        field_instance.bind_to_container(name, field_index, byte_offset)
        if byte_offset is not None and field_instance.size is not None:
            byte_offset += field_instance.size
        else:
            byte_offset = None

        meta.components[name] = field_instance
        field_index += 1
        n_fields_found += 1

    meta.size_bytes = byte_offset
    meta.num_own_fields = n_fields_found

    def _decorator() -> Type["Struct"]:
        return class_object

    return _decorator
