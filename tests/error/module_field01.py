#Assignment to a module field can only at the constructor
from polyphony import module


@module
class module_field01:
    def __init__(self):
        self.append_worker(self.func)

    def func(self):
        self.x = 10


m = module_field01()
