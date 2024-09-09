"""Support for declaring fields in structs using `PEP 526`_ variable annotations.

You can use the :func:`dataclass` decorator on your :class:`Struct`.

If you use this decorator, *all* fields must be declared with PEP 526 annotations. You
can't mix this system with the original assignment-based one.

Here are a few examples of how you can declare your fields::

    @binobj.dataclass
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

.. versionadded:: 0.9.0

.. deprecated:: 0.11.0
    Do not pass a callable as the default value, use the ``factory`` argument to the
    field instead.

.. _PEP 526: https://www.python.org/dev/peps/pep-0526/
"""

from __future__ import annotations

import dataclasses
import typing
import warnings
from typing import Any
from typing import Optional
from typing import TypeVar
from typing import Union

from binobj import errors
from binobj import fields
from binobj.structures import Struct


if typing.TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Sequence

    from typing_extensions import Self

    from binobj.fields.base import Field


__all__ = ["dataclass"]


TStruct = TypeVar("TStruct", bound=Struct)


def flatten_annotations(annotation: Any) -> list[Any]:
    """Convert an annotation that *might* be a :class:`typing.Annotated` into a list.

    This is very similar to :func:`more_itertools.always_iterable`, except for type
    annotations. Single annotations are converted to a one-element list; PEP-593
    annotations are flattened into a list and returned.
    """
    if not hasattr(annotation, "__metadata__"):
        return [annotation]
    return list(annotation.__metadata__)


@dataclasses.dataclass
class AnnotationInfo:
    name: str
    """The name of the field."""

    type_class: Any
    """The type annotation's core class.

    For the most part this will be

    * A Field class,
    * A Field instance, or
    * A Struct class.

    If the field was marked as Optional[X], this will be X and :attr:`nullable` will be
    True.
    """

    type_args: Sequence[Any] = ()
    """Arguments passed to the annotation.

    This is here for forward compatibility and should be ignored for now.
    """

    has_default: Optional[bool] = None
    default_value: Any = fields.UNDEFINED

    nullable: bool = False
    """Indicates if this field can be None or not."""

    @classmethod
    def from_annotation(
        cls, field_name: str, annotation: Any, struct_class: type[TStruct]
    ) -> Self:
        type_class = annotation
        type_args = typing.get_args(annotation)
        nullable = type(None) in type_args

        # Handle Optional[T] which gets rendered as Union[T, type(None)].
        # We have to compare types directly with `is` because the type annotations don't
        # support isinstance() and issubclass().
        if typing.get_origin(type_class) is Union:
            # Filter out None from the type arguments.
            type_args = tuple(t for t in type_args if t is not type(None))

            if len(type_args) != 1:
                # If we get here then the type annotation for this field is a Union with
                # two or more types. This means the caller is probably attempting to
                # declare a `binobj.fields.Union`.
                raise errors.InvalidTypeAnnotationError(
                    field=field_name, annotation=annotation
                )

            # The type annotation was Optional[T]. Pretend the annotation was T, and
            # resolve *its* arguments just in case T is of the form X[Y, ...].
            type_class = type_args[0]
            type_args = typing.get_args(type_class)

        default_value = getattr(struct_class, field_name, fields.UNDEFINED)
        if callable(default_value):
            warnings.warn(
                "Passing a bare callable as the default value was a misfeature. Use"
                " the `factory` keyword argument instead.",
                DeprecationWarning,
                stacklevel=2,
            )

        return cls(
            name=field_name,
            type_class=type_class,
            type_args=type_args,
            has_default=hasattr(struct_class, field_name),
            default_value=default_value,
            nullable=nullable,
        )

    def make_field_instance(self) -> Optional[Field[Any]]:
        """Convert a type annotation to a Field object if it represents one."""
        if isinstance(self.type_class, type):
            # We got a class object. Could be a struct or field, ignore everything else.
            if issubclass(self.type_class, Struct):
                # A Struct class is shorthand for Nested(Struct).
                return fields.Nested(self.type_class)
            if issubclass(self.type_class, fields.Field):
                # This is a Field class. Initialize it with only the arguments we're
                # certain of. This gives us a Field instance.
                kw: dict[str, Any]
                kw = {"null_value": fields.DEFAULT} if self.nullable else {}

                return self.type_class(name=self.name, default=self.default_value, **kw)

            # Else: Not a struct or field class -- ignore
            return None

        if not isinstance(self.type_class, fields.Field):
            # Not an instance of Field -- ignore
            return None

        # Else: The annotation is a field instance.
        return self.type_class


def dataclass(class_object: type[TStruct]) -> type[TStruct]:
    """Mark a Struct as using `PEP 526`_ declarations for its fields.

    If you use this decorator, *all* fields must be declared with PEP 526 annotations.
    You can't mix this system with the original assignment-based one.

    Here are a few examples of how you can declare your fields::

        @binobj.dataclass
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

    For compatibility with type checkers, use :class:`typing.Annotated`. The struct
    above would be declared like this::

        @binobj.dataclass
        class MyStruct(binobj.Struct):
            foo: Annotated[int, UInt16]
            bar: Annotated[str, StringZ] = ""

            # We don't need Annotated[...] here because type checkers will expect the
            # same annotation that BinObj uses.
            sub_struct: MyOtherStruct

            baz: Annotated[datetime, Timestamp64(signed=False)]

    .. versionadded:: 0.9.0

    .. _PEP 526: https://www.python.org/dev/peps/pep-0526/
    """
    meta = class_object.__binobj_struct__
    if meta.num_own_fields > 0:
        raise errors.MixedDeclarationsError(struct=class_object)

    field_index = 0
    n_fields_found = 0
    byte_offset = meta.size_bytes
    all_annotations = typing.get_type_hints(class_object, include_extras=True)

    for name, raw_annotation in all_annotations.items():
        flattened_annotations = flatten_annotations(raw_annotation)

        info_list = [
            AnnotationInfo.from_annotation(name, ann, class_object)
            for ann in flattened_annotations
        ]
        derived_field_instances = [
            field
            for info in info_list
            if (field := info.make_field_instance()) is not None
        ]

        if len(derived_field_instances) > 1:
            raise errors.ConfigurationError(
                f"Field {name!r} of struct {class_object} has"
                f" {len(derived_field_instances)} valid BinObj annotations. There must"
                " be at most one.",
                field=name,
                struct=class_object,
            )
        if not derived_field_instances:
            continue

        field_instance = derived_field_instances[0]

        if name in meta.components:
            # Puke -- the field was already defined in the superclass.
            raise errors.FieldRedefinedError(struct=class_object.__name__, field=name)

        field_instance.bind_to_container(meta, name, field_index, byte_offset)
        if byte_offset is not None and field_instance.has_fixed_size:
            byte_offset += typing.cast(int, field_instance.size)
        else:
            byte_offset = None

        meta.components[name] = field_instance
        field_index += 1
        n_fields_found += 1

        # Overwrite the field declaration in the class with the derived field instance
        # object. Otherwise, we'll end up with None or the default value provided:
        #
        #  class MyStruct:
        #      foo: UInt8 = 123
        #
        # If we don't do this `MyStruct.foo` will be `123`, not a Field object.
        setattr(class_object, name, field_instance)

    if n_fields_found == 0:
        raise errors.NoDefinedFieldsError(struct=class_object)

    meta.size_bytes = byte_offset
    meta.num_own_fields = n_fields_found
    return class_object
