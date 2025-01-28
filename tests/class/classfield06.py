from polyphony import testbench


V1 = 1
V2 = 1 + V1 + 0

class C:
    class D:
        class E:
            V3 = V1 + V2
        i = (V1, V2, E.V3)
    i = (D.i[2], D.i[2], D.i[0])

def classfield06(x):
    return C.i[x]


@testbench
def test():
    assert 3 == classfield06(0)
    assert 3 == classfield06(1)
    assert 1 == classfield06(2)
