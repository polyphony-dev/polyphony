from polyphony import testbench

def list04(x):
    a = [1,2,3,4,5,6,7,8]
    b = [None]*12

    while True:
        for i in range(0, 8):
            b[i] = a[i]
        break
    return b[x]

@testbench
def test():
    assert 1 == list04(0)
    assert 5 == list04(4)
