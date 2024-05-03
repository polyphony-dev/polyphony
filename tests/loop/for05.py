from polyphony import testbench

def for05(x):
    s1 = 0
    s2 = 0
    for i in range(x):
        s1 += 1
        s2 += 2
        if i == 5:
            continue
    return s1 + s2

@testbench
def test():
    assert 0 == for05(0)
    assert 3 == for05(1)
    assert 30 == for05(10)
