import polyphony
from subpkg.sub1 import SubC
import subpkg.sub1


def import_pkg03_a1(x):
    subc = SubC(x)
    return subc.x


def import_pkg03_a2(x):
    subc = subpkg.sub1.SubC(x)
    return subc.x


def import_pkg03_b1():
    return SubC.VALUE1


def import_pkg03_b2():
    return subpkg.sub1.SubC.VALUE1


def import_pkg03_c1(x):
    return SubC.VALUE2[x]


def import_pkg03_c2(x):
    return subpkg.sub1.SubC.VALUE2[x]


@polyphony.testbench
def test():
    assert 100 == import_pkg03_a1(10)
    assert 100 == import_pkg03_a2(10)
    assert 1234 == import_pkg03_b1()
    assert 1234 == import_pkg03_b2()
    assert 1 == import_pkg03_c1(0)
    assert 1 == import_pkg03_c2(0)
    assert 4 == import_pkg03_c1(3)
    assert 4 == import_pkg03_c2(3)
