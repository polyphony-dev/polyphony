import polyphony
import sub1
import sub2
from sub1 import func2 as func2_1
from sub2 import func2 as func2_2


def import06_a1(x):
    return sub1.func1(x) + sub2.func1(x)


def import06_a2(x):
    return func2_1(x) + func2_2(x)


@polyphony.testbench
def test():
    assert 31 == import06_a1(10)
    assert 42 == import06_a2(10)


test()
