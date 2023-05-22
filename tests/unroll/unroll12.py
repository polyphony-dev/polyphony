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
def unroll12_a(xs:List[int][5], a):
    if a == 0:
        shift_full(xs, 0)
    elif a == 1:
        shift_full(xs, 1)
    else:
        shift_full(xs, 2)


def unroll12_b(xs, a):
    if a == 0:
        shift_2(xs, 0)
    elif a == 1:
        shift_2(xs, 1)
    else:
        shift_2(xs, 2)


def unroll12():
    xs = [1, 2, 3, 4, 5]
    unroll12_a(xs, 0)
    assert 0 == xs[0]
    assert 1 == xs[1]
    assert 2 == xs[2]
    assert 3 == xs[3]
    assert 4 == xs[4]
    unroll12_a(xs, 1)
    assert 1 == xs[0]
    assert 0 == xs[1]
    assert 1 == xs[2]
    assert 2 == xs[3]
    assert 3 == xs[4]
    unroll12_a(xs, 2)
    assert 2 == xs[0]
    assert 1 == xs[1]
    assert 0 == xs[2]
    assert 1 == xs[3]
    assert 2 == xs[4]
    unroll12_a(xs, 3)
    assert 2 == xs[0]
    assert 2 == xs[1]
    assert 1 == xs[2]
    assert 0 == xs[3]
    assert 1 == xs[4]

    xs = [1, 2, 3, 4, 5]
    unroll12_b(xs, 0)
    assert 0 == xs[0]
    assert 1 == xs[1]
    assert 2 == xs[2]
    assert 3 == xs[3]
    assert 4 == xs[4]
    unroll12_b(xs, 1)
    assert 1 == xs[0]
    assert 0 == xs[1]
    assert 1 == xs[2]
    assert 2 == xs[3]
    assert 3 == xs[4]
    unroll12_b(xs, 2)
    assert 2 == xs[0]
    assert 1 == xs[1]
    assert 0 == xs[2]
    assert 1 == xs[3]
    assert 2 == xs[4]
    unroll12_b(xs, 3)
    assert 2 == xs[0]
    assert 2 == xs[1]
    assert 1 == xs[2]
    assert 0 == xs[3]
    assert 1 == xs[4]


@testbench
def test():
    unroll12()

test()