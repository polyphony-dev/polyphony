from polyphony import testbench

def while05(x):
    s1 = 0
    s2 = 0
    i = 0
    while True:
        s1 += 1
        while True:
            i += 1 + x
            s2 += 2
            if i < 5:
                continue
            elif i < 7:
                continue
            else:
                break
        s1 += 0
        if s1 > 5:
            break
    return s1 + s2

@testbench
def test():
    assert 30 == while05(0)
    assert 24 == while05(1)
    assert 22 == while05(2)
