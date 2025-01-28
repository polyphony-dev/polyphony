from polyphony import testbench

def list16(x, y):
    data = [0, 1, 2]
    while True:
        if x == 0:
            return 0
            #pass
        else:
            x = x + 1
            if y == 0:
                d = data[0]
            elif y == 2:
                data[0] = y
                d = data[0]
            else:
                d = 0
        break
    return d + x

@testbench
def test():
    assert 0 == list16(0, 1)
    assert 4 == list16(1, 2)
    assert 2 == list16(1, 0)
