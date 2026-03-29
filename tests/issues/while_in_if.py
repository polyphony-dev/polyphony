"""
Issue: while loop inside nested if blocks causes LPHIRemover IndexError.
LPHIRemover.process() at phiopt.py:73 raises IndexError on lphi.args[update_idx]
because the LPHI args count does not match the loop head's predecessor count
when the while loop is syntactically nested inside if blocks.

Error: IndexError: tuple index out of range
  File "polyphony/compiler/ir/transformers/phiopt.py", line 73, in process
    update_arg = lphi.args[update_idx]
"""
from polyphony import module, testbench
from polyphony.modules import Handshake
from polyphony.typing import List


@module
class WhileInIf:
    def __init__(self):
        self.din = Handshake(int, "in")
        self.dout = Handshake(int, "out")
        self.append_worker(self.worker)

    def scale(self, a, b):
        return (a * b + 16384) >> 15

    def worker(self):
        s:List[int] = [0] * 8
        i = 0
        while i < 8:
            s[i] = self.din.rd()
            i = i + 1

        # Compute a condition
        flag = s[0]

        # while loop inside nested if: triggers the bug
        if flag > 0:
            if flag <= 4:
                k = 0
                while k < 8:
                    s[k] = self.scale(s[k], flag)
                    k = k + 1

        i = 0
        while i < 8:
            self.dout.wr(s[i])
            i = i + 1


@testbench
def test():
    m = WhileInIf()
    for i in range(8):
        m.din.wr(i + 1)
    for i in range(8):
        result = m.dout.rd()
