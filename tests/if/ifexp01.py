from polyphony import testbench

def ifexp01(x, y):
    return True if x == y else False

@testbench
def test():
    assert False == ifexp01(0, 1)
    assert True == ifexp01(1, 1)
    assert False == ifexp01(True, False)
