import polyphony
import subpkg
from subpkg.sub1 import func1, func2
import subpkg.subsubpkg2.subsub2


def import_pkg05_1(x):
    return subpkg.sub1.func1(x)


def import_pkg05_2(x):
    return func1(x)


def import_pkg05_3(x):
    return subpkg.subsubpkg2.subsub2.func2(x)


def import_pkg05_4(x):
    return func2(x)


@polyphony.testbench
def test():
    assert import_pkg05_1(10) == import_pkg05_2(10)
    assert import_pkg05_3(10) == import_pkg05_4(10)


test()
