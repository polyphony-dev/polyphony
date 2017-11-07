#The type of @module class argument must be constant, not list[int[32]]
from polyphony import module


@module
class module_args01:
    def __init__(self, arg):
        pass


m = module_args01([1, 2, 3])
