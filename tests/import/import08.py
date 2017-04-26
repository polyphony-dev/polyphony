import polyphony
from sub1 import SubC as Sub1
from sub2 import SubC as Sub2


def import08_a1():
    return Sub1.VALUE1


def import08_a2():
    return Sub2.VALUE1


def import08_b1(x):
    return Sub1.VALUE2[x]


def import08_b2(x):
    return Sub2.VALUE2[x]


@polyphony.testbench
def test():
    assert 1234 == import08_a1()
    assert 5678 == import08_a2()
    assert 1 == import08_b1(0)
    assert 5 == import08_b2(0)


test()
