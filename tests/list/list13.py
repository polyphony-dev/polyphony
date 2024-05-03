from polyphony import testbench

def list13(x):
    reg = [1,2,3,4]
    mem = [None] * 64
    for i in range(64):
        mem[i] = 0
    for i in range(4):
        mem[i] = reg[i]

    return mem[x] + mem[1] + mem[2] + mem[3]

@testbench
def test():
    assert 10 == list13(0)
