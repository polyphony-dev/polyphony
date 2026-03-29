from polyphony import testbench


def typed_list_func(data):
    return data[0] + data[1]


@testbench
def test():
    assert typed_list_func([1, 2]) == 3
