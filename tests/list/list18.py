from polyphony import testbench

def list18(x, y):
    insts = [0, 1, 2, 3]
    r = [0]*4
    r[0] = x
    i = 0
    while True:
        inst = insts[i]
        if inst == 0:
            r[0] = x
        elif inst == 1:
            r[1] = y
        elif inst == 2:
            r[2] = r[0] + r[1]
        elif inst == 3:
            break
        i += 1
    return r[2]

@testbench
def test():
    assert 1 == list18(0, 1)
    assert 2 == list18(1, 1)
    assert 3 == list18(2, 1)
