from polyphony import testbench
from polyphony import unroll as ur


def unroll03_a(x):
    sum = 0
    for i in ur(range(10), 2):
        for j in ur(range(10)):
            sum += (i * j * x)
    return sum


def unroll03_b(x):
    sum = 0
    for i in ur(range(10)):
        for j in ur(range(10)):
            sum += (i * j * x)
    return sum


@testbench
def test():
    assert 2025 == unroll03_a(1)
    assert 4050 == unroll03_a(2)
    assert 2025 == unroll03_b(1)
    assert 4050 == unroll03_b(2)
