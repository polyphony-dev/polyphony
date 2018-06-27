#There is a read conflict at 'xs' in a pipeline
from polyphony import testbench
from polyphony import rule


def pipeline_resource01(xs, ys):
    with rule(scheduling='pipeline'):
        for i in range(4):
            a = xs[i]
            b = xs[i + 1]
            ys[i] = (a + b) >> 1
    return


@testbench
def test():
    out = [None] * 400
    pipeline_resource01([1, 2, 3, 4] * 100, out)


test()
