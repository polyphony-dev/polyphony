from ..subsubpkg2.subsub2 import func2 as f2
from .. import subsubpkg2


def func1(x):
    return f2(x)


def func2(x):
    return subsubpkg2.subsub2.func2(x)
