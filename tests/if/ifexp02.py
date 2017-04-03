from polyphony import testbench

def ifexp02(x, y):
    return 1 if x > y else -1 if y > x else 0

@testbench
def test():
    assert -1 == ifexp02(0, 1)
    assert 1 == ifexp02(1, 0)
    assert 0 == ifexp02(1, 1)

test()
