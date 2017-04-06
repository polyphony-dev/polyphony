from polyphony import pure
from polyphony import testbench


@pure
def data(op, x):
    if op == 'mul':
        return [i * i for i in range(x)]
    elif op == 'add':
        return [i + i for i in range(x)]


class C:
    d0 = data('mul', 10)
    d1 = data('add', 10)


def pure08_a(idx):
    return C.d0[idx]


def pure08_b(idx):
    return C.d1[idx]


@testbench
def test():
    assert 0 == pure08_a(0)
    assert 25 == pure08_a(5)
    assert 81 == pure08_a(9)

    assert 0 == pure08_b(0)
    assert 10 == pure08_b(5)
    assert 18 == pure08_b(9)


test()
