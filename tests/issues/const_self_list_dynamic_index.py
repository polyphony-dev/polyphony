"""
Issue: self list initialized with literals produces wrong code with dynamic index.
constopt treats literal-initialized self lists as constants. When accessed
with a dynamic index in the worker, compilation succeeds but produces wrong
results (returns 0 instead of the correct table value).
When accessed in a helper method, it fails with:
  "A global or class variable must be a constant value"
See also: inlined_method_local_list.py
"""
from polyphony import module, testbench
from polyphony.modules import Handshake


@module
class ConstSelfList:
    def __init__(self):
        self.inp = Handshake(int, 'in')
        self.out = Handshake(int, 'out')
        self.table = [10, 20, 30, 40, 50, 60, 70, 80]
        self.append_worker(self.worker)

    def worker(self):
        idx = self.inp.rd()
        result = self.table[idx]
        self.out.wr(result)


@testbench
def test():
    m = ConstSelfList()
    m.inp.wr(3)
    result = m.out.rd()
    print(result)
    assert result == 40
