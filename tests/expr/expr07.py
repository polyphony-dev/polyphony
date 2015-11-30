from polyphony import testbench

def expr07(a, b):
    return a > b

@testbench
def test():
    assert False == expr07(0, 0)
    assert False  == expr07(0, 1)
    assert True == expr07(1, 0)
    assert False == expr07(-1, 0)
    assert False == expr07(-2, -1)
    assert True == expr07(1, -1)

test()
