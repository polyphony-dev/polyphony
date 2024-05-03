from polyphony import testbench

def expr06(a, b):
    return a < b

@testbench
def test():
    assert False == expr06(0, 0)
    assert True  == expr06(0, 1)
    assert False == expr06(1, 0)
    assert True == expr06(-1, 0)
    assert True == expr06(-2, -1)
    assert False == expr06(1, -1)
