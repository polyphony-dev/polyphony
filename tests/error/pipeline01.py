#Cannot use 'break' statement in the pipeline loop
from polyphony import testbench
from polyphony import pipelined


def pipeline01():
    s = 0
    for i in pipelined(range(10)):
        if s > 10:
            break
        s += i
    return s


@testbench
def test():
    pipeline01()


test()
