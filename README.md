# annotatation-tools
A Package inspried by typer's unique [function inspection logic](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/utils.py#L107) and
turns configuring your own into a smaller system with a lot of 
boilerplate code removed out of the equation allowing for 
different instances or even multiple different translations 
of annotations to take place.

It can be used to build your own argument parser libaries
that utilize function annotations but there is literally more to it
than just that.

```python
from dataclasses import dataclass
from typing import Annotated

from annotation_tools import IGNORE, Inspector


@dataclass
class A:
    value: int


@dataclass
class B:
    value: str


def translate(name: str, origin: type, annotation, default):
    # annotations that are not belonging to the provided system
    # can also be translated the same as type origin.
    # the system could easily be expanded upon as functools.partial 
    # or even a class method can easily lift the loads even more.
    if issubclass(origin, str):
        return B(name)

    # returning Ignore means that this translated type should be dismissed.
    return IGNORE


def func(a: Annotated[int, A(1)], b: str):
    return b


def main():
    translator = Inspector(A, B, translator=IGNORE)
    # {'a': Param(name='a', default=<class 'inspect._empty'>, annotation=A(value=1)), 
    # 'b': Param(name='b', default=<class 'inspect._empty'>, annotation=IGNORE)}
    print(translator.inspect(func))

    # you can also translate missing annotations 
    translator2 = Inspector(A, B, translator=translate)
    # {'a': Param(name='a', default=<class 'inspect._empty'>, annotation=A(value=1)), 
    # 'b': Param(name='b', default=<class 'inspect._empty'>, annotation=B(value='b'))}
    print(translator2.inspect(func))


if __name__ == "__main__":
    main()
```
