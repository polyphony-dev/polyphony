from polyphony import testbench

def while01(x):
    s1 = 0
    s2 = 0
    i = 0
    while i < x:
        s1 += i
        s2 += i
        i = i + 1
    return s1 + s2

@testbench
def test():
    assert 0 == while01(0)
    assert 0 == while01(1)
    assert 2 == while01(2)
