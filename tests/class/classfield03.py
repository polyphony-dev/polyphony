from polyphony import testbench

class C:
    i = (1, 2, 3)
    j = (1, 2, 3)
    k = i[j[0]] + i[j[1]]

def classfield03():
    return C.k

@testbench
def test():
    assert 5 == classfield03()

test()
