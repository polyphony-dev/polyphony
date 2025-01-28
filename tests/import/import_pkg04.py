import polyphony
from subpkg import SUBPKG_CONSTANT_100
from subpkg import SUBPKG_CONSTANT_111 as const111


def import_pkg04_1():
    return SUBPKG_CONSTANT_100


def import_pkg04_2():
    return const111


@polyphony.testbench
def test():
    assert 100 == import_pkg04_1()
    assert 111 == import_pkg04_2()
