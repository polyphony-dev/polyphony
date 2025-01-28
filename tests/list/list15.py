from polyphony import testbench

def list15(x):
    #rom = [1, 2, 3, 4, 5]
    ram = [0] * 5
    ram[0] = 1
    ram[1] = 2
    ram[2] = 3
    ram[3] = 1
    ram[4] = 5
    if x != 0:
        y = len(ram) - x
    else:
        y = 0
    return ram[x] + ram[y]

@testbench
def test():
    assert 2 == list15(0)
    assert 7 == list15(1)
    assert 4 == list15(2)
    assert 4 == list15(3)
    assert 7 == list15(4)
