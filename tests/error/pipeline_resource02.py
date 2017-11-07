#Cannot write 'ys' more than once in a pipeline loop
from polyphony import testbench
from polyphony import rule


def pipeline_resource02(xs, ys):
    with rule(scheduling='pipeline'):
        for i in range(4):
            a = xs[i]
            ys[i] = a
            ys[i + 1] = a << 1
    return


@testbench
def test():
    out = [None] * 400
    pipeline_resource02([1, 2, 3, 4] * 100, out)


test()
