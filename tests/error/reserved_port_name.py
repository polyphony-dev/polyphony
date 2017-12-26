#The name of Port 'clk' is reserved
from polyphony import module
from polyphony.io import Port


@module
class reserved_port_name:
    def __init__(self):
        self.clk = Port(bool, 'out')


m = reserved_port_name()
