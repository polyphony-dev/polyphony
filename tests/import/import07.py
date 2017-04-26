import polyphony
import sub1
import sub2
import sub3


def import07_a1(x):
    return sub1.func3(x) + sub2.func3(x)


def import07_a2(x):
    return sub3.func1(x) + sub3.func1(x) + 30


@polyphony.testbench
def test():
    print(import07_a1(10))
    assert 250 == import07_a1(10)
    assert 250 == import07_a2(10)


test()
