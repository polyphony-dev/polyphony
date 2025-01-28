from polyphony import testbench

def for03(x):
    s1 = 0
    s2 = 0
    for i in range(x):
        s1 += 1
        if i == 5:
            continue
        s2 += 2
    return s1 + s2

@testbench
def test():
    assert 0 == for03(0)
    assert 3 == for03(1)
    assert 28 == for03(10)
