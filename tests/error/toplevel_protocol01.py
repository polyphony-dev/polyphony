#Port type of 'port' cannot be resolved; protocol modules (e.g. Handshake) must be used as fields of a @module class, not as top-level instances
from polyphony import testbench
from polyphony.modules import Handshake
from polyphony.typing import int8

hs = Handshake(int8, 'out')

@testbench
def test():
    hs.wr(42)
