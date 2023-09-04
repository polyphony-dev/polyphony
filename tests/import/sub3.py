from polyphony import testbench


SUB3_GLOBAL = 333
SUB3_GLOBAL_ARRAY1 = (31, 32, 33, 34)
SUB3_GLOBAL_ARRAY2 = (35, 36, 37, 38)


def func1(x):
    return x + 100


@testbench
def sub_test():
    assert 100 == func1(0)


if __name__ == '__main__':
    sub_test()
