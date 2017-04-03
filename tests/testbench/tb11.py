from polyphony import testbench

def f(t, i, tt, ii):
    return t[i] + tt[ii]

@testbench
def test():
    rom = (0, 1, 2)
    assert 1 == f(rom, 0, rom, 1)
    assert 3 == f(rom, 1, rom, 2)
    assert 2 == f(rom, 2, rom ,0)

test()
