"""A MyPy plugin for properly interpreting field types."""

import functools
from types import ModuleType
from typing import Callable
from typing import Optional
from typing import Type

import mypy.plugin
import pkg_resources
from mypy.plugin import AnalyzeTypeContext
from mypy.plugin import AttributeContext
from mypy.types import Type as MyPyType
from typing_extensions import Final

from binobj.fields import containers
from binobj.fields import numeric
from binobj import pep526
from binobj.fields import stringlike


_IMPORT_PREFIX_TO_MODULE = {
    "binobj.fields.containers": containers,
    "binobj.fields.numeric": numeric,
    "binobj.fields.stringlike": stringlike,
    "binobj.pep526": pep526,
}


MIN_SUPPORTED_MYPY_VERSION: Final = pkg_resources.parse_version("0.730")


def plugin(version: str) -> Optional[Type["BinObjPlugin"]]:
    """Get the plugin class if this MyPy version is supported."""
    plugin_version = pkg_resources.parse_version(version)

    if plugin_version < MIN_SUPPORTED_MYPY_VERSION:
        return None
    return BinObjPlugin


class BinObjPlugin(mypy.plugin.Plugin):
    """A MyPy plugin that adds support for BinObj fields and structs."""

    def get_type_analyze_hook(
        self, fullname: str
    ) -> Optional[Callable[[AnalyzeTypeContext], MyPyType]]:
        # TODO (dargueta)
        return None

    def get_attribute_hook(
        self, fullname: str
    ) -> Optional[Callable[[AttributeContext], MyPyType]]:
        """Interpret the datatype of a field and lie to MyPy about it.

        Arguments:
            fullname (str):
                The name of the attribute with the full import path of the class, e.g.
                ``mylib.module.MyClass.attribute_name``.

        Returns:
            None if the type couldn't be determined, otherwise a callable that returns
            MyPy type information.
        """
        module_and_class, _sep, attribute_name = fullname.rpartition(".")
        module_name, _sep, class_name = module_and_class.rpartition(".")

        if module_name not in _IMPORT_PREFIX_TO_MODULE:
            return None

        module = _IMPORT_PREFIX_TO_MODULE[module_name]
        return functools.partial(
            determine_type,
            module=module,
            class_name=class_name,
            attribute_name=attribute_name,
        )


def determine_type(
    context: AttributeContext,
    *,
    module: ModuleType,
    class_name: str,
    attribute_name: str
) -> MyPyType:
    raise NotImplementedError
