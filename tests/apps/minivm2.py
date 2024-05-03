import polyphony
from polyphony import Channel
from polyphony.io import Port
from polyphony.modules import Handshake
from polyphony.typing import int8, uint8, uint16
from polyphony.timing import timed, clkfence

@timed
@polyphony.module
class MiniVM:
    LOAD0 = 0
    LOAD1 = 1
    ADD = 2
    SUB = 3
    MUL = 4
    HALT = 0xFF

    def __init__(self, start_addr, end_addr):
        self.dout = Handshake(int8, 'out')
        self.ch_inst = Channel(uint16, capacity=1)
        self.ch_ope  = Channel(uint16, capacity=1)
        self.ch_value = Channel(uint16, capacity=1)
        self.reg0 = 0
        self.reg1 = 0
        self.append_worker(self.fetch, loop=True)
        self.append_worker(self.decode, loop=True)
        self.append_worker(self.execute, loop=True)
        self.program = (0x0001, 0x0102, 0x0200, 0x0103, 0x0200, 0xFF00,  # 1 + 2 + 3
                        0x0002, 0x0103, 0x0400, 0x0104, 0x0400, 0xFF00)  # 2 * 3 * 4
        self.pc = start_addr
        self.end_addr = end_addr

    def fetch(self):
        instruction = self.program[self.pc]
        self.ch_inst.put(instruction)
        if self.pc < self.end_addr:
            self.pc += 1

    def decode(self):
        inst = self.ch_inst.get()
        op = (inst & 0xFF00) >> 8
        v  = (inst & 0x00FF)
        self.ch_ope.put(op)
        self.ch_value.put(v)

    def execute(self):
        op = self.ch_ope.get()
        v = self.ch_value.get()
        if op == MiniVM.LOAD0:
            self.reg0 = v
        elif op == MiniVM.LOAD1:
            self.reg1 = v
        elif op == MiniVM.ADD:
            self.reg0 = self.reg0 + self.reg1
        elif op == MiniVM.SUB:
            self.reg0 = self.reg0 - self.reg1
        elif op == MiniVM.MUL:
            self.reg0 = self.reg0 * self.reg1
        elif op == MiniVM.HALT:
            self.dout.wr(self.reg0)


@polyphony.testbench
def test():
    vm0 = MiniVM(0, 5)
    d = vm0.dout.rd()
    assert d == 6

    vm1 = MiniVM(6, 11)
    d = vm1.dout.rd()
    assert d == 24

