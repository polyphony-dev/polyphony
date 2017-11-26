#Cannot use 'continue' statement in the pipeline loop
from polyphony import testbench
from polyphony import pipelined


def pipeline02():
    s = 0
    for i in pipelined(range(10)):
        if s > 10:
            continue
        s += i
    return s


@testbench
def test():
    pipeline02()


test()
