import polyphony
from sub1 import SubC
import sub1


def import05_a1(x):
    subc = SubC(x)
    return subc.x


def import05_a2(x):
    subc = sub1.SubC(x)
    return subc.x


def import05_b1():
    return SubC.VALUE1


def import05_b2():
    return sub1.SubC.VALUE1


def import05_c1(x):
    return SubC.VALUE2[x]


def import05_c2(x):
    return sub1.SubC.VALUE2[x]


@polyphony.testbench
def test():
    assert 100 == import05_a1(10)
    assert 100 == import05_a2(10)
    assert 1234 == import05_b1()
    assert 1234 == import05_b2()
    assert 1 == import05_c1(0)
    assert 1 == import05_c2(0)
    assert 4 == import05_c1(3)
    assert 4 == import05_c2(3)


test()
