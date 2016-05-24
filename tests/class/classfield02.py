from polyphony import testbench

class C:
    i = [1, 2, 3]

def classfield02(i):
    return C.i[i]

@testbench
def test():
    assert 1 == classfield02(0)
    assert 2 == classfield02(1)
    assert 3 == classfield02(2)

test()
