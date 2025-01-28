from polyphony import testbench


def f1(b):
    if b == 0:
        pass

    if b == 1:
        return 1

    return 2


def if16():
    return f1(0)


@testbench
def test():
    assert 2 == if16()
