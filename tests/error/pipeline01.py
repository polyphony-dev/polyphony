#Cannot use 'break' statement in the pipeline loop
from polyphony import testbench
from polyphony import rule


def pipeline01():
    with rule(scheduling='pipeline'):
        s = 0
        for i in range(10):
            if s > 10:
                break
            s += i
    return s


@testbench
def test():
    pipeline01()


test()
