#Cannot use 'continue' statement in the pipeline loop
from polyphony import testbench
from polyphony import rule


def pipeline02():
    with rule(scheduling='pipeline'):
        s = 0
        for i in range(10):
            if s > 10:
                continue
            s += i
    return s


@testbench
def test():
    pipeline02()


test()
