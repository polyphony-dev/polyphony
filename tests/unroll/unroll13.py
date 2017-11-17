from polyphony import testbench
from polyphony import unroll


def accum2_a(xs, ys, size):
    temp = 0
    for j in unroll(range(size)):
        temp += xs[size - j - 1] * ys[j]

    for j in unroll(range(size)):
        temp += xs[j] * ys[j]
    return temp


def accum2_b(xs, ys, size):
    temp = 0
    for j in unroll(range(size), 2):
        temp += xs[size - j - 1] * ys[j]

    for j in unroll(range(size)):
        temp += xs[j] * ys[j]
    return temp


def accum2_c(xs, ys, size):
    temp = 0
    for j in unroll(range(size)):
        temp += xs[size - j - 1] * ys[j]

    for j in unroll(range(size), 2):
        temp += xs[j] * ys[j]
    return temp


def accum2_d(xs, ys, size):
    temp = 0
    for j in unroll(range(size), 2):
        temp += xs[size - j - 1] * ys[j]

    for j in unroll(range(size), 2):
        temp += xs[j] * ys[j]
    return temp


def unroll13_a(v0, v1, v2, v3):
    xs = [1, 2, 3, 4]
    ys = [v0, v1, v2, v3] * 4
    return accum2_a(xs, ys, len(xs))


def unroll13_b(v0, v1, v2, v3):
    xs = [1, 2, 3, 4]
    ys = [v0, v1, v2, v3] * 4
    return accum2_b(xs, ys, len(xs))


def unroll13_c(v0, v1, v2, v3):
    xs = [1, 2, 3, 4]
    ys = [v0, v1, v2, v3] * 4
    return accum2_c(xs, ys, len(xs))


def unroll13_d(v0, v1, v2, v3):
    xs = [1, 2, 3, 4]
    ys = [v0, v1, v2, v3] * 4
    return accum2_d(xs, ys, len(xs))


@testbench
def test():
    print(unroll13_a(1, 2, 1, 4))
    print(unroll13_b(1, 2, 1, 4))
    print(unroll13_c(1, 2, 1, 4))
    print(unroll13_d(1, 2, 1, 4))


test()
