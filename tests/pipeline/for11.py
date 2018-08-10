from polyphony import testbench
from polyphony import pipelined
from polyphony import rule

def pipe11(xs, ys):
    for i in pipelined(range(len(xs) - 1), ii=2):
        v = xs[i] + xs[i + 1]
        v >>= 1
        ys[i] = v

@testbench
def test():
    idata = [0, 16, 32, -16, -64]
    odata = [0] * 5
    pipe11(idata, odata)
    assert 8 == odata[0]
    assert 24 == odata[1]
    assert 8 == odata[2]
    assert -40 == odata[3]
    assert 0 == odata[4]


test()
