#Normal function cannot be pipelined
from polyphony import testbench
from polyphony import rule


@rule(scheduling='pipeline')
def pipeline03():
    s = 0
    for i in range(10):
        s += i
    return s


@testbench
def test():
    pipeline03()


test()
