from polyphony import testbench

def for04(x):
    s1 = 0
    s2 = 0
    for i in range(x):
        s1 += 1
        s2 += 2
        if i == 5:
            break
    return s1 + s2

@testbench
def test():
    assert 0 == for04(0)
    assert 3 == for04(1)
    assert 18 == for04(10)
