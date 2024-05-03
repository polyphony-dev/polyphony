import polyphony
from sub1 import SubC as Sub1
from sub2 import SubC as Sub2
from sub1 import get_v


def import09_a1(x):
    return get_v(Sub1(x))


#def import09_a2(x):
#    return get_v(Sub2(x))


@polyphony.testbench
def test():
    assert 100 == import09_a1(10)
    #assert 1000 == import09_a2(10)
