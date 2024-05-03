from polyphony import testbench


def func(spam, ham, eggs):
    return spam, ham, eggs


def kwargs01(idx, spam, ham, eggs):
    t = func(spam=spam, ham=ham, eggs=eggs)
    return t[idx]


@testbench
def test():
    assert 0 == kwargs01(0, spam=0, ham=1, eggs=2)
    assert 1 == kwargs01(1, spam=0, ham=1, eggs=2)
    assert 2 == kwargs01(2, spam=0, ham=1, eggs=2)
    assert 2 == kwargs01(0, spam=2, ham=3, eggs=4)
    assert 3 == kwargs01(1, spam=2, ham=3, eggs=4)
    assert 4 == kwargs01(2, spam=2, ham=3, eggs=4)
