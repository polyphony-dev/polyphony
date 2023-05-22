from polyphony import testbench


def list30(k0, v):
    buf0 = [v] * 100
    ref0 = buf0
    while True:
        buf0 = ref0
        ref0 = buf0
        if k0:
            break
    return ref0[0]


@testbench
def test():
    assert 3 == list30(1, 3)


test()