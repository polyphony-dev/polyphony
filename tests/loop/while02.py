from polyphony import testbench

def while02(x):
    s1 = 0
    s2 = 0
    i = 0
    while i < x:
        s1 += 1
        if i == 5:
            break
        s2 += 2
        i += 1
    return s1 + s2

@testbench
def test():
    assert 0 == while02(0)
    assert 3 == while02(1)
    assert 6 == while02(2)

test()
