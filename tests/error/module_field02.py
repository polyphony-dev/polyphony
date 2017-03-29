#Assignment to a module port can only be done once
from polyphony import module
from polyphony.io import Port


@module
class module_field02:
    def __init__(self):
        self.x = Port(int)
        self.x = Port(int)


m = module_field02()
