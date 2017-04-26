import polyphony
from sub1 import func1
import sub1


def func2(x):
    return 0


def import04(x):
    a = func1(x)
    b = sub1.func2(x)
    c = func2(x)
    return a + b + c


@polyphony.testbench
def test():
    assert 11 == func1(10)
    assert 3 == sub1.func2(1)
    assert 0 == func2(1)
    assert 5 == import04(1)


test()
