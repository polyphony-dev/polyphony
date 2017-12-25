#Assignment to a module field can only at the constructor
from polyphony import module


class Statefull:
    def __init__(self, v):
        self.v0 = v

    def func(self):
        if self.v0 == 0:
            self.v0 = 1
        elif self.v0 == 1:
            self.v0 = 2
        else:
            self.v0 = 0
        return self.v0


@module
class module_field03:
    def __init__(self):
        self.append_worker(self.worker0)
        self.append_worker(self.worker1)
        self.obj = Statefull(10)

    def worker0(self):
        print(self.obj.func())

    def worker1(self):
        print(self.obj.func())


m = module_field03()
