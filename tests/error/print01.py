#print() takes only scalar type (e.g. int, str, ...) argument
from polyphony import testbench


@testbench
def test():
    print([1, 2, 3])


test()
