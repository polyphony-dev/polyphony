"""
Bug: Testbench writes 0 instead of the correct 64-bit constant to Handshake port.

In the generated Verilog testbench, writing a constant > 32 bits via
Handshake.wr() produces `t_din_data <= 0` instead of the correct value.
The assertion check in the same testbench correctly uses the large constant,
so the issue is specific to the Handshake write codegen path.

Python simulation works correctly; only HDL simulation fails.
"""
from polyphony import testbench
from polyphony import module
from polyphony.modules import Handshake
from polyphony.typing import bit64


@module
class PassThrough:
    def __init__(self):
        self.din = Handshake(bit64, "in")
        self.dout = Handshake(bit64, "out")
        self.append_worker(self.main)

    def main(self):
        a = self.din.rd()
        self.dout.wr(a)


@testbench
def test():
    m = PassThrough()
    m.din.wr(0x100000000)
    result = m.dout.rd()
    assert result == 0x100000000
