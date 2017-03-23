#Calling a method of the module class can only in the module itself
from polyphony import module


@module
class module_method01:
    def __init__(self):
        pass

    def func(self):
        pass


m = module_method01()
m.func()
