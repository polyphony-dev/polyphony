from polyphony import testbench

@testbench
def test():
    rom = [10, 11, 12]
    for i in range(3):
        assert rom[i] == i + 10
        print(rom[i])
