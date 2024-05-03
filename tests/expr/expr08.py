from polyphony import testbench

def expr08(a, b, c):
    return a < b < c

@testbench
def test():
    assert False == expr08(0, 0, 0)
    assert True  == expr08(0, 1, 2)
    assert False == expr08(1, 0, 2)
    assert False == expr08(2, 1, 0)
    assert True == expr08(-1, 0, 1)
    assert True == expr08(-2, -1, 0)
