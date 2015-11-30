from polyphony import testbench

def f(l:list, i):
    assert i >= 0 and i < 3
    return l[i]

@testbench
def test():
    rom = [0, 1, 2]
    assert 0 == f(rom, 0)
    assert 1 == f(rom, 1)
    assert 2 == f(rom, 2)
