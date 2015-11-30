from polyphony import testbench

def for06(x, y):
    s1 = 0
    s2 = 0
    for i in range(x, y):
        s1 += 1
        s2 += 2
        if i > 5:
            break
        if i <= 5:
            continue
    return s1 + s2

@testbench
def test():
    assert 0 == for06(0, 0)
    assert 3 == for06(0, 1)
    assert 6 == for06(5, 10)

test()
