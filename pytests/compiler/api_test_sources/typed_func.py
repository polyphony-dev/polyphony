from polyphony import testbench


def typed_func(a, b):
    return a + b


@testbench
def test():
    assert typed_func(1, 2) == 3
