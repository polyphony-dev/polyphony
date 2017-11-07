from polyphony import testbench


class C:
    class D:
        i = (1, 2, 3)
    i = [D.i[2], D.i[2], D.i[0]]


def classfield06(x):
    return C.i[x]


@testbench
def test():
    assert 3 == classfield06(0)
    assert 3 == classfield06(1)
    assert 1 == classfield06(2)


test()
