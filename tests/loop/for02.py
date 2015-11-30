from polyphony import testbench

def for02(x):
    s1 = 0
    s2 = 0
    for i in range(x):
        s1 += 1
        if i == 5:
            break
        s2 += 2
    return s1 + s2

@testbench
def test():
    assert 0 == for02(0)
    assert 3 == for02(1)
    assert 16 == for02(10)

test()
