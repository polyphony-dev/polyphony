from polyphony import testbench

def list14(x):
    rom = [1, None, 3, None, 5]
    ram = [2, None, 4, None, 6]
    ram[1] = 3
    return rom[0] + ram[1] + x

@testbench
def test():
    assert 4 == list14(0)
