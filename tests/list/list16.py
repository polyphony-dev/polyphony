from polyphony import testbench

def list16(data:list, x, y):

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
    return d

@testbench
def test():
    d = [0, 1, 2]
    assert 0 == list16(d, 0, 1)
    assert 2 == list16(d, 1, 2)
    assert 2 == list16(d, 1, 0)
test()
