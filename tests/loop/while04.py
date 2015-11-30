from polyphony import testbench

def while04(x):
    s1 = 0
    s2 = 0
    i = x
    while True:
        s1 += 1
        if i >= 5:
            break
        s2 += 2
        i += 1
    return s1 + s2

@testbench
def test():
    assert 16 == while04(0)
    assert 13 == while04(1)
    assert 10 == while04(2)

test()
