import polyphony
import sub1
from sub3 import SUB3_GLOBAL


def import10_a():
    return sub1.SUB1_GLOBAL


def import10_b():
    return SUB3_GLOBAL


@polyphony.testbench
def test():
    assert 111 == import10_a()
    assert 333 == import10_b()


test()
