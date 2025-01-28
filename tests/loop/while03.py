from polyphony import testbench

def while03(x):
    s1 = 0
    s2 = 0
    i = 0
    while i < x:
        s1 += 1
        if i == 5:
            i += 1
            continue
        s2 += 2
        i += 1
    return s1 + s2

@testbench
def test():
    assert 0 == while03(0)
    assert 3 == while03(1)
    assert 28 == while03(10)
