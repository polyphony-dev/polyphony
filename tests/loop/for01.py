from polyphony import testbench

def for01(x):
    s1 = 0
    s2 = 0
    for i in range(x):
        s1 += i
        s2 += i
    return s1 + s2

@testbench
def test():
    assert 0 == for01(0)
    assert 0 == for01(1)
    assert 2 == for01(2)

test()
