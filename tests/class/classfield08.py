from polyphony import testbench


class C:
    class D:
        i = (10, 20, 30)

    class E:
        i = (100, 200, 300)


def classfield08(x):
    return C.D.i[x] + C.E.i[x]


@testbench
def test():
    assert 110 == classfield08(0)
    assert 220 == classfield08(1)
    assert 330 == classfield08(2)


test()
