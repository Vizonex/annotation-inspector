import dataclasses
import inspect
import sys
from collections.abc import Callable, Sequence
from typing import (
    Annotated,
    Any,
    ClassVar,
    TypeVar,
    final,
    get_args,
    get_origin,
    get_type_hints,
)

if sys.version_info >= (3, 13):  # pragma: no cover
    from typing import TypeVarTuple
else:
    from typing_extensions import TypeVarTuple

if sys.version_info < (3, 15):
    from typing_extensions import Sentinel as sentinel


__version__ = "0.1.0"
__all__ = (
    "IGNORE",
    "AnnotationError",
    "DuplicateAnnotationsError",
    "Inspector",
    "Param",
    "TranslationError",
)

# Much of this work is inpired by typer but is intended to simplifiy
# Annotation translation logic for other developers.

# Marks that parser can ignore converstion of
# this said annotation.
IGNORE = sentinel("IGNORE")
"""Used during translation to determine if a return type
should be considered ignoreable and is used to mark ignorable
annotations or a group of arguments that are exempt from 
translation. returning None on any given translation is treated 
as an automatic failure."""

_Ts = TypeVarTuple("_Ts", default=())

# Overloading and correctness of different types.
A = TypeVar("A")


@dataclasses.dataclass(slots=True)
class Param:
    """defines a translated result"""

    empty: ClassVar[inspect.Parameter.empty] = inspect.Parameter.empty
    name: str
    """name of the parameter"""
    default: Any | inspect.Parameter.empty = inspect.Parameter.empty
    """default parameter if none given or provided."""
    annotation: Any | inspect.Parameter.empty = inspect.Parameter.empty
    """Collected, inspected or translated annotation."""


class AnnotationError(TypeError):
    """Annotation could not be translated"""

    def __init__(self, type_arg: Any) -> None:
        self._type_arg = type_arg

    def __str__(self) -> str:
        return f"`Annotated` type {type(self._type_arg).__name__!r} is not implemented."


class TranslationError(TypeError):
    """Failed to translate provided argument type `arg: *this*`
    to statisfied annotations."""

    def __init__(self, type_arg: type[Any]) -> None:
        self._type_arg = type_arg

    def __str__(self) -> str:
        return f"Unable to translate `Argument` type {self._type_arg.__name__!r} to an annotation."


class DuplicateAnnotationsError(ValueError):
    def __init__(self, args: Sequence[type[Any]]) -> None:
        self._args = args

    def __str__(self) -> str:
        return f"Duplicate `Annotations` for {self._args!r}"


def split_annotation(base: type[Any], *valid_annotation_types: *_Ts):
    """Splits up annotations"""
    if get_origin(base) is not Annotated:
        return base, [], []
    base_annotation, *maybe_valid_annotations = get_args(base)
    return (
        base_annotation,
        [
            annotation
            for annotation in maybe_valid_annotations
            if not isinstance(annotation, valid_annotation_types)
        ],
        [
            annotation
            for annotation in maybe_valid_annotations
            if isinstance(annotation, valid_annotation_types)
        ],
    )


@final
class Inspector:
    """Inspects and translates different annotations during funciton inspection."""

    __slots__ = ("_inspector", "_translator", "_types")

    # Having a single annotated_type argument followed by a
    # *annotated_types forces 1 or more types to work with.
    def __init__(
        self,
        annotated_type: type[Any],
        *annotated_types: type[Any],
        translator: Callable[[str, type, type, Any], Any | IGNORE]
        | IGNORE
        | None = None,
        inspector: Callable[[Param], Any] | None = None,
    ) -> None:
        """
        :param annotated_types: list of types to look for
            before determining if conversion methods are
            acceptable.

        :param translator: callback for translating
            annotations that aren't a specific type
            or when none are given. the callback arguments
            in order are the arg_name, arg_type
            and arg_annotation, arg_default
            the annotation will be different from the target
            annotated types that need different translations.
            If callback is set to IGNORE, the :class:`Inspector`
            simply becomes a annotations gatherer that ignores
            unneeded annotations.

        :param inspector: callback that inspects correct annotations
            it can be used to catch or correct any inappropriate arrangements.

        :rasies ValueError:
            when annotated_types are not given.

        """
        if translator and translator != IGNORE and not callable(translator):
            raise TypeError(
                f"translator argument {type(translator).__name__!r} must be callable"
            )

        if inspector and not callable(inspector):
            raise TypeError(
                f"inspector argument {type(inspector).__name__!r} must be callable"
            )

        types = [annotated_type]
        types.extend(annotated_types)
        self._types = tuple(types)
        self._translator = translator
        self._inspector = inspector

    def inspect(
        self,
        func: Callable[..., Any],
        exclude_args: Sequence[str] | set[str] | None = None,
        ignore_exclusions: bool = False,
    ) -> dict[str, Param]:
        """
        Inspects a function and translates it's contents into
        desired annotation types.

        :param func: a function to translate off.
        :param exclude_args: a list of arguments that can
            be expempt from being translated.
            It is primarly useful when labeling dependency
            injections or ignoring certain arguments
            such as a user context variable.

        :param ignore_exclusions: Ignores adding
            `IGNORE` sentiel type to translated annotation and the paramter itself entirely.
            parameters will not remeber the name of this argument or anything about it.

        :rasies TranslationError:
            when type callback returns with None or the type did not change or isn't a provided
            annotation.

        """

        if inspect.isclass(func):
            try:
                func = func.__init__
            except AttributeError:  # pragma: no cover - pypy special case
                return {}

        elif not inspect.isroutine(func):  # pragma: no cover
            # this is a very rare special case that can't be easily triggered.
            try:
                func = func.__call__
            except AttributeError:  # pragma: no cover - pypy special case
                return {}

        signature = inspect.signature(func, eval_str=True)
        parameters = dict(signature.parameters)

        excluded = exclude_args or []
        type_hints = get_type_hints(func)
        params = {}
        for param in parameters.values():
            if param.name in excluded:
                if not ignore_exclusions:
                    params[param.name] = Param(param.name, param.default, IGNORE)
                continue

            base, different, matching = split_annotation(param.annotation, *self._types)

            if len(matching) > 1:
                raise DuplicateAnnotationsError(matching)

            elif len(different) > 1:
                raise DuplicateAnnotationsError(different)

            if matching:
                if inspector := self._inspector:
                    inspector(Param(param.name, param.default, matching[0]))
                annotation = matching.pop()

            elif param.name in type_hints:
                # Resolve forward references.
                annotation = type_hints[param.name]
            else:
                annotation = base

            if not isinstance(annotation, self._types):
                if translate := self._translator:
                    if translate == IGNORE:
                        annotation = IGNORE
                    else:
                        annotation = translate(
                            param.name, base, annotation, param.default
                        )

                if not isinstance(annotation, self._types):
                    if annotation == IGNORE:
                        # user has requested to ignore this translation
                        if not ignore_exclusions:
                            params[param.name] = Param(
                                param.name, param.default, IGNORE
                            )
                        continue
                    # Diagnose the problem It is errors from here on out.
                    if base == annotation or annotation is None:
                        # arg: *type* is incorrectly translated or unimplemented
                        raise TranslationError(base)
                    else:
                        # Annotation incorrectly trasnlated.
                        raise AnnotationError(annotation)

            params[param.name] = Param(param.name, param.default, annotation=annotation)
        return params
