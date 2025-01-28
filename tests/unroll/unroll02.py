from polyphony import testbench, rule
from polyphony import unroll
from polyphony.timing import clktime

def unroll02_full():
    xs = [10, 20, 30, 40, 50, 60, 70, 80]
    sum = 0
    for x in unroll(xs):
        sum += x
    return sum


def unroll02_factor2():
    xs = [10, 20, 30, 40, 50, 60, 70, 80]
    sum = 0
    for x in unroll(xs, 2):
        sum += x
    return sum


def unroll02_factor1():
    xs = [10, 20, 30, 40, 50, 60, 70, 80]
    sum = 0
    for x in unroll(xs, 1):
        sum += x
    return sum


def unroll02_no_unroll():
    xs = [10, 20, 30, 40, 50, 60, 70, 80]
    sum = 0
    for x in xs:
        sum += x
    return sum


@rule(scheduling='sequential')
@testbench
def test1():
    assert 360 == unroll02_full()
    print(clktime())
    assert 5 == clktime()

@rule(scheduling='sequential')
@testbench
def test2():
    assert 360 == unroll02_factor2()
    print(clktime())
    assert 9 == clktime()

@rule(scheduling='sequential')
@testbench
def test3():
    assert 360 == unroll02_factor1()
    print(clktime())
    assert 13 == clktime()

@rule(scheduling='sequential')
@testbench
def test4():
    assert 360 == unroll02_no_unroll()
    print(clktime())
    assert 13 == clktime()
