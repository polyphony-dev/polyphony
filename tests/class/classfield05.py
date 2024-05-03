from polyphony import testbench


class D:
    i = (1, 2, 3)


class C:
    i = (D.i[2], D.i[2], D.i[0])


def classfield05(x):
    return C.i[x]


@testbench
def test():
    assert 3 == classfield05(0)
    assert 3 == classfield05(1)
    assert 1 == classfield05(2)
