from .subsubpkg.subsub1 import func2 as sub_f2

SUB1_GLOBAL = 111
SUB1_GLOBAL_ARRAY = [1, 2, 3, 4]
SUB1_GLOBAL_TUPLE = (5, 6, 7, 8)


def func1(x):
    return x + 1


def func2(x):
    return sub_f2(x)


def get_v(c):
    return c.v()


class SubC:
    VALUE1 = 1234
    VALUE2 = (1, 2, 3, 4)

    def __init__(self, x):
        self.x = x * x

    def v(self):
        return self.x
