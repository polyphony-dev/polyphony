from polyphony import testbench


def f1(b):
    if b:
        return 1
    else:
        return 2


def f2(b):
    return f1(b)


def if15():
    return f2(False) + f1(True)


@testbench
def test():
    assert 3 == if15()


test()
