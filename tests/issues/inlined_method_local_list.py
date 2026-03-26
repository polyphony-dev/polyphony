"""
Issue: Helper method accessing self literal-list with dynamic index fails compilation.
When a literal-initialized self list is accessed in a helper method with
a dynamic index (from another self list), constopt fails to constant-fold.
Error: "A global or class variable must be a constant value"
"""
from polyphony import module, testbench
from polyphony.modules import Handshake


@module
class InlinedMethodList:
    def __init__(self):
        self.inp = Handshake(int, 'in')
        self.out = Handshake(int, 'out')
        self.table = [10, 20, 30, 40, 50, 60, 70, 80]
        self.data = [0] * 8
        self.append_worker(self.worker)

    def lookup(self):
        # Access self.table indexed by self.data[0] (dynamic)
        self.data[1] = self.table[self.data[0]]

    def worker(self):
        idx = self.inp.rd()
        self.data[0] = idx
        self.lookup()
        self.out.wr(self.data[1])


@testbench
def test():
    m = InlinedMethodList()
    m.inp.wr(3)
    assert m.out.rd() == 40
