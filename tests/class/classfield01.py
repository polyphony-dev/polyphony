from polyphony import testbench

class C:
    j = 1
    i = 1233 + j

def classfield01():
    return C.i

@testbench
def test():
    assert 1234 == classfield01()
