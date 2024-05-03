from polyphony import testbench


def func(spam, ham, eggs):
    return spam, ham, eggs


def kwargs02(idx, spam, ham, eggs):
    t = func(spam, eggs=eggs, ham=ham)
    return t[idx]


@testbench
def test():
    assert 0 == kwargs02(0, eggs=2, spam=0, ham=1)
    assert 1 == kwargs02(1, ham=1, eggs=2, spam=0)
    assert 2 == kwargs02(2, spam=0, ham=1, eggs=2)
    assert 2 == kwargs02(0, 2, ham=3, eggs=4)
    assert 3 == kwargs02(1, 2, 3, eggs=4)
    assert 4 == kwargs02(idx=2, spam=2, ham=3, eggs=4)
