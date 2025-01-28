from polyphony import testbench
from polyphony import pipelined
from polyphony.typing import List, int16

def pipe_func(xs, ys):
    for i in pipelined(range(len(xs))):
        v = xs[i]
        if v < 0:
            vv = (v - 8)
            z = vv >> 4
        else:
            vv = (v + 8)
            z = vv >> 4
        print('z', z)
        ys[i] = z


def for06():
    data:List[int16] = [0, 16, 32, -16, -64]
    out:List[int16] = [0] * 5
    pipe_func(data, out)
    assert 0 == out[0]
    assert 1 == out[1]
    assert 2 == out[2]
    assert -2 == out[3]
    assert -5 == out[4]

@testbench
def test():
    for06()
