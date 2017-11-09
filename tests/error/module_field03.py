#The module class cannot access an object
from polyphony import module
from polyphony.io import Port


class Obj:
    def func(self):
        return 1


@module
class module_field03:
    def __init__(self):
        self.x = Port(int, 'in')
        self.o = Obj()
        self.append_worker(self.w)

    def w(self):
        self.o.func()


m = module_field03()
