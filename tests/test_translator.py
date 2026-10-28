from dataclasses import dataclass
from typing import Annotated

import pytest

from annotation_tools import (
    IGNORE,
    AnnotationError,
    DuplicateAnnotationsError,
    Inspector,
    Param,
    TranslationError,
)


@dataclass
class A:
    value: int


@dataclass
class B:
    value: str


@dataclass
class Sub(B):
    pass


class EmptyClass:
    pass


@dataclass
class ClassWithArg:
    a: Annotated[int, A(1)]

def func1(a: Annotated[int, A(1)], b: str) -> None:
    pass


def func2(a: Annotated[int, A(1)], b: Annotated[str, B("value")]) -> None:
    pass


def func3(a: int, b: Annotated[str, B("value")]) -> None:
    pass


def func4(a: int, b: Annotated[str, Sub("value")]) -> None:
    pass


# 5th signature has an ignored annotation.
def func5(a, b: Annotated[str, Sub("value")]) -> None:
    pass


def func6(a: int, b: Annotated[str, B("value"), A(1)]) -> None:
    pass


class Class:
    def method(self, a: Annotated[int, A(1)] = 1):
        pass


class TestInspector:
    def test_function_inspection(self) -> None:
        t = Inspector(A, translator=IGNORE)
        results = t.inspect(func1)
        assert results == {
            "a": Param(name="a", default=Param.empty, annotation=A(value=1)),
            "b": Param(name="b", default=Param.empty, annotation=IGNORE),
        }

    def test_method_inspection(self):
        t = Inspector(A, translator=IGNORE)
        results = t.inspect(Class.method)
        assert results["a"].annotation == A(1)
        assert results["a"].default == 1

    def test_ignorable_annotations(self) -> None:
        t = Inspector(A, translator=IGNORE)
        results = t.inspect(func2)
        # These shoudln't equal because the Inspector was set to only find annotations
        # related to class "A"
        assert results["b"] != Param("b", default=Param.empty, annotation=B("value"))

    def test_multiple_annotations(self) -> None:
        t = Inspector(A, B, translator=IGNORE)
        results = t.inspect(func2)
        # We asked for both A & B so A and B should be provided.
        assert results["a"] == Param(
            name="a", default=Param.empty, annotation=A(value=1)
        )
        assert results["b"] == Param("b", default=Param.empty, annotation=B("value"))

    def test_treating_subclassed_annotations_as_acceptable(self):
        t = Inspector(A, B, translator=IGNORE)
        results = t.inspect(func4)
        # Subclasses are valid types also.
        assert results["b"].annotation == Sub("value")

    def test_unknown_type(self) -> None:
        t = Inspector(B, translator=IGNORE)
        results = t.inspect(func5)
        assert results["a"].annotation == IGNORE

    def test_class_inspection(self):
        # classes are allowed example: a modified version of typer with
        # dependency config dataclasses?
        t = Inspector(A, translator=IGNORE)
        results = t.inspect(ClassWithArg)
        assert results["a"].annotation == A(1)

    def test_exclusions(self) -> None:
        t = Inspector(B, translator=IGNORE)
        params = t.inspect(func3, exclude_args=["a"])
        assert params["a"].annotation == IGNORE
        assert params["b"].annotation == B("value")

    def test_ignored_exclusions(self) -> None:
        t = Inspector(B, translator=IGNORE)
        params = t.inspect(func3, exclude_args=["a"], ignore_exclusions=True)
        assert "a" not in params
        assert params["b"].annotation == B("value")


def translate_1(name: str, origin, annotation, default) -> B:
    if issubclass(origin, str):
        return B(name)
    # FAIL
    return


def translate_2(name: str, origin, annotation, default) -> B:
    if issubclass(origin, str):
        return B(name)
    # FAIL
    return A(0xDEAD)


class TestTranslation:
    def test_translating_empty_annotations(self):
        t = Inspector(A, B, translator=translate_1)
        results = t.inspect(func1)
        # This should result in translating non-provided annotations to a given one.
        assert results["b"].annotation == B("b")

    def test_inspection(self):
        inspected = False

        def inspector(param: Param):
            nonlocal inspected
            inspected = True
            assert issubclass(type(param.annotation), (A, B))

        t = Inspector(A, B, translator=IGNORE, inspector=inspector)
        t.inspect(func1)
        assert inspected


class TestErrors:
    def test_wrong_callable(self):
        with pytest.raises(
            TypeError, match=r"translator argument 'int' must be callable"
        ):
            _ = Inspector(A, B, translator=1)

    def test_wrong_inspector(self):
        with pytest.raises(
            TypeError, match=r"inspector argument 'str' must be callable"
        ):
            _ = Inspector(A, B, inspector="uh oh")

    def test_type_translation_error(self):
        t = Inspector(A, B, translator=translate_1)

        with pytest.raises(
            TranslationError,
            match=r"Unable to translate `Argument` type 'int' to an annotation.",
        ):
            _ = t.inspect(func3)

    def test_error_for_inappropriate_annotation(self) -> None:
        """wrong annotation given that isn't seen by the translation part of the inspector as a valid type."""
        t = Inspector(B, translator=translate_2)

        with pytest.raises(
            AnnotationError, match=r"`Annotated` type 'A' is not implemented."
        ):
            _ = t.inspect(func3)

    def test_duplicates_matching(self) -> None:
        t = Inspector(A, B, translator=IGNORE)
        with pytest.raises(
            DuplicateAnnotationsError, match=r"Duplicate `Annotations` for .*"
        ):
            _ = t.inspect(func6)

    def test_duplicates_different(self) -> None:
        t = Inspector(Sub, translator=IGNORE)
        with pytest.raises(
            DuplicateAnnotationsError, match=r"Duplicate `Annotations` for .*"
        ):
            _ = t.inspect(func6)
