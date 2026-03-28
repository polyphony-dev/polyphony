"""
Bug: unsigned 64-bit (bit64) values with bit63 set are misinterpreted as
signed negative values in Python sim and csim.

Root cause: the compiler's type inference propagates signedness from Python
integer literals into intermediate variables. When `bit64 // int_literal`
is computed, the result gets the 'int' tag (signed) in AHDL. The Python sim's
Reg/Net.set() then applies twos_comp(), turning unsigned values with bit63
set into negative Python ints.

HDL sim (iverilog) handles this correctly because reg [63:0] is unsigned.
"""
from polyphony import testbench
from polyphony import module
from polyphony.modules import Handshake
from polyphony.typing import bit64


@module
class Unsigned64Div:
    def __init__(self):
        self.din = Handshake(bit64, "in")
        self.dout = Handshake(bit64, "out")
        self.append_worker(self.main)

    def main(self):
        x = self.din.rd()
        # Compute 0x8000000000000000 internally (avoids testbench constant
        # truncation bug).
        a:bit64 = x << 63
        # Floor division: 0x8000000000000000 // 2
        # Should give 0x4000000000000000 (= 2^62).
        # Bug: compiler infers result type as signed from literal '2',
        # so Python sim stores it as -2^62 via twos_comp.
        result:bit64 = a // 2
        self.dout.wr(result)


@testbench
def test():
    m = Unsigned64Div()

    m.din.wr(1)
    d = m.dout.rd()
    print(d)
    # Expected: 0x4000000000000000 = 4611686018427387904
    assert d == 0x4000000000000000
