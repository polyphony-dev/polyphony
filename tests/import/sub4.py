from polyphony import testbench
from polyphony import module
from polyphony.io import Port

VALUE = 100

@module
class sub4:
    def __init__(self, param=10):
        self.i = Port(int, 'in', init=VALUE)
        self.o = Port(int, 'out')
        self.param = param

@testbench
def sub_test():
    pass


if __name__ == '__main__':
    sub_test()
