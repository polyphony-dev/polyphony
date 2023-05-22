from polyphony import testbench


def list31(k0):
    buf0 = [0] * 100
    buf1 = [0] * 100
    
    ref0 = buf0
    ref1 = buf1
    i = 0
    k = k0
    x = 0
    while True:
        ref0[x] = k
        x += 1
        k += 1
        if x == 100:
            x = 0
            if i % 2 == 0:
                ref0 = buf1
                ref1 = buf0
            else:
                ref0 = buf0
                ref1 = buf1
            i = 1 - i
        if k > 200:
            break
    for i in range(100):
        assert i + 1 == buf0[i]
    for i in range(100):
        assert i + 101 == buf1[i]

@testbench
def test():
    list31(1)


test()
