"""
Issue: Large worker method with complex control flow causes STG builder Phi assertion.
When a worker has many branches and loop nesting, the generated Phi nodes
can have only 1 argument, violating the assertion len(ir.args) > 1.
Error: assert ir.ps and len(ir.args) == len(ir.ps) and len(ir.args) > 1 (stgbuilder.py)
"""
from polyphony import module, testbench
from polyphony.modules import Handshake


@module
class LargeWorkerPhi:
    def __init__(self):
        self.out = Handshake(int, 'out')
        self.append_worker(self.worker)

    def worker(self):
        data = [0] * 16
        ret = [0] * 16
        result = 0

        # Phase 1: fill data with branches
        i = 0
        while i < 16:
            if i < 4:
                data[i] = i + 1
            elif i < 8:
                data[i] = (i - 4) * 2
            elif i < 12:
                data[i] = (i - 8) * 3
            else:
                data[i] = (i - 12) * 4
            i = i + 1

        # Phase 2: nested loops with branches (similar to AES encrypt rounds)
        round_idx = 0
        while round_idx < 3:
            j = 0
            while j < 4:
                x = data[j * 4] + data[1 + j * 4]
                if (x >> 4) == 1:
                    x = x ^ 27
                ret[j * 4] = x
                x = data[1 + j * 4] + data[2 + j * 4]
                if (x >> 4) == 1:
                    x = x ^ 27
                ret[1 + j * 4] = x
                x = data[2 + j * 4] + data[3 + j * 4]
                if (x >> 4) == 1:
                    x = x ^ 27
                ret[2 + j * 4] = x
                x = data[3 + j * 4] + data[j * 4]
                if (x >> 4) == 1:
                    x = x ^ 27
                ret[3 + j * 4] = x
                j = j + 1
            j = 0
            while j < 4:
                data[j * 4] = ret[j * 4]
                data[1 + j * 4] = ret[1 + j * 4]
                data[2 + j * 4] = ret[2 + j * 4]
                data[3 + j * 4] = ret[3 + j * 4]
                j = j + 1
            round_idx = round_idx + 1

        # Phase 3: more nested loops with branches (similar to AES decrypt rounds)
        round_idx = 2
        while round_idx >= 0:
            j = 0
            while j < 4:
                x = data[j * 4] - data[1 + j * 4]
                if x < 0:
                    x = x + 256
                ret[j * 4] = x
                x = data[1 + j * 4] - data[2 + j * 4]
                if x < 0:
                    x = x + 256
                ret[1 + j * 4] = x
                x = data[2 + j * 4] - data[3 + j * 4]
                if x < 0:
                    x = x + 256
                ret[2 + j * 4] = x
                x = data[3 + j * 4] - data[j * 4]
                if x < 0:
                    x = x + 256
                ret[3 + j * 4] = x
                j = j + 1
            j = 0
            while j < 4:
                data[j * 4] = ret[j * 4]
                data[1 + j * 4] = ret[1 + j * 4]
                data[2 + j * 4] = ret[2 + j * 4]
                data[3 + j * 4] = ret[3 + j * 4]
                j = j + 1
            round_idx = round_idx - 1

        i = 0
        while i < 16:
            result = result + data[i]
            i = i + 1
        self.out.wr(result)


@testbench
def test():
    m = LargeWorkerPhi()
    d = m.out.rd()
    print(d)


