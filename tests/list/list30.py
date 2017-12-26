from polyphony import testbench


def list30(k0, buf0):
    ref0 = buf0
    while True:
        buf0 = ref0
        ref0 = buf0
        if k0:
            break
    return ref0[0]


@testbench
def test():
    buf0 = [0] * 100
    assert 0 == list30(1, buf0)


test()