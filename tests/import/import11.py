import polyphony
import sub1
from sub3 import SUB3_GLOBAL_ARRAY, SUB3_GLOBAL_TUPLE


def import11_a(i):
    return sub1.SUB1_GLOBAL_ARRAY[i]


def import11_b(i):
    return sub1.SUB1_GLOBAL_TUPLE[i]


def import11_c(i):
    return SUB3_GLOBAL_ARRAY[i]


def import11_d(i):
    return SUB3_GLOBAL_TUPLE[i]

def import11_e():
    return len(SUB3_GLOBAL_ARRAY)


@polyphony.testbench
def test():
    assert 1 == import11_a(0)
    assert 3 == import11_a(2)
    assert 6 == import11_b(1)
    assert 8 == import11_b(3)
    assert 31 == import11_c(0)
    assert 33 == import11_c(2)
    assert 36 == import11_d(1)
    assert 38 == import11_d(3)
    assert 4 == import11_e()


test()
