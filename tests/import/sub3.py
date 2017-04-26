from polyphony import testbench


def func1(x):
    return x + 100


@testbench
def sub_test():
    assert 100 == func1(0)


sub_test()
