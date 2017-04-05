from polyphony import preprocess as pre
from polyphony import testbench


@pre
def data(op, x):
    if op == 'mul':
        return [i * i for i in range(x)]
    elif op == 'add':
        return [i + i for i in range(x)]


class C:
    d0 = data('mul', 10)
    d1 = data('add', 10)


def preprocess08_a(idx):
    return C.d0[idx]


def preprocess08_b(idx):
    return C.d1[idx]


@testbench
def test():
    assert 0 == preprocess08_a(0)
    assert 25 == preprocess08_a(5)
    assert 81 == preprocess08_a(9)

    assert 0 == preprocess08_b(0)
    assert 10 == preprocess08_b(5)
    assert 18 == preprocess08_b(9)


test()
