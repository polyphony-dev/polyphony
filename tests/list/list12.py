from polyphony import testbench

def list12(x):
    reg1 = [0] * 32
    reg2 = [10, 12, 14]
    reg1[0] = reg2[0]
    reg1[1] = reg2[1]
    reg1[2] = reg2[2]
        
    return reg1[0] + reg1[1] + reg1[2]

@testbench
def test():
    assert 36 == list12(3)
test()
