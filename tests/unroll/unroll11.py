from polyphony import testbench
from polyphony import unroll
from polyphony.typing import List


def shift_full(xs:list, x):
    for j in unroll(range(len(xs) - 1)):
        jj = (len(xs) - 1) - j
        xs[jj] = xs[jj - 1]
    xs[0] = x


def shift_2(xs:list, x):
    for j in unroll(range(len(xs) - 1), 2):
        jj = (len(xs) - 1) - j
        xs[jj] = xs[jj - 1]
    xs[0] = x


# For full unroll, the argument list must specify an explicit size.
def unroll11_a(xs:List[int][5]):
    shift_full(xs, 1)
    shift_full(xs, 2)
    shift_full(xs, 3)
    shift_full(xs, 4)
    shift_full(xs, 5)


def unroll11_b(xs):
    shift_2(xs, 1)
    shift_2(xs, 2)
    shift_2(xs, 3)
    shift_2(xs, 4)
    shift_2(xs, 5)


def unroll11():
    xs = [1, 2, 3, 4, 5]
    unroll11_a(xs)
    assert 5 == xs[0]
    assert 4 == xs[1]
    assert 3 == xs[2]
    assert 2 == xs[3]
    assert 1 == xs[4]

    xs = [1, 2, 3, 4, 5]
    unroll11_b(xs)
    assert 5 == xs[0]
    assert 4 == xs[1]
    assert 3 == xs[2]
    assert 2 == xs[3]
    assert 1 == xs[4]


@testbench
def test():
    unroll11()
