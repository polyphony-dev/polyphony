import polyphony
from polyphony.io import Port, Queue
from polyphony.typing import int8, uint8, uint16

@polyphony.module
class MiniVM:
    LOAD0 = 0
    LOAD1 = 1
    ADD = 2
    SUB = 3
    MUL = 4
    HALT = 0xFF

    def __init__(self, start_addr):
        # define i/o
        self.dout = Port(int8, protocol='ready_valid')

        # define internals
        instq = Queue(uint16, maxsize=2)
        opeq = Queue(uint8, maxsize=2)
        valueq = Queue(uint8, maxsize=2)

        self.append_worker(fetch, start_addr, instq)
        self.append_worker(decode, instq, opeq, valueq)
        self.append_worker(execute, opeq, valueq, self.dout)


def fetch(start_addr, instq):
    pc = start_addr
    program = [0x0001, 0x0102, 0x0200, 0x0103, 0x0200, 0xFF00,  # 1 + 2 + 3
               0x0002, 0x0103, 0x0400, 0x0104, 0x0400, 0xFF00]  # 2 * 3 * 4

    while polyphony.is_worker_running():
        if len(program) <= pc:
            break
        instruction = program[pc]
        pc += 1
        instq.wr(instruction)


def decode(instq, opeq, valueq):
    while polyphony.is_worker_running():
        inst = instq.rd()
        op = (inst & 0xFF00) >> 8
        v  = (inst & 0x00FF)
        opeq.wr(op)
        valueq.wr(v)


def execute(opeq, valueq, dout):
    reg0 = 0
    reg1 = 0
    while polyphony.is_worker_running():
        op = opeq.rd()
        v = valueq.rd()

        if op == MiniVM.LOAD0:
            reg0 = v
        elif op == MiniVM.LOAD1:
            reg1 = v
        elif op == MiniVM.ADD:
            reg0 = reg0 + reg1
        elif op == MiniVM.SUB:
            reg0 = reg0 - reg1
        elif op == MiniVM.MUL:
            reg0 = reg0 * reg1
        elif op == MiniVM.HALT:
            dout.wr(reg0)
            break


@polyphony.testbench
def vm0_test(vm0):
    d = vm0.dout.rd()
    assert d == 6


@polyphony.testbench
def vm1_test(vm1):
    d = vm1.dout.rd()
    assert d == 24


# instantiate synthesizing module
vm0 = MiniVM(0)
vm1 = MiniVM(6)

vm0_test(vm0)
vm1_test(vm1)
