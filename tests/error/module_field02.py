#Assignment to a module field can only be done once
from polyphony import module
from polyphony.io import Port


@module
class module_field02:
    def __init__(self):
        self.x = Port(int, 'in')
        self.x = Port(int, 'out')


m = module_field02()
