from polyphony import testbench
from polyphony import pipelined


def minivm(program):
    MOV = 0
    ADD = 1
    SUB = 2
    MUL = 3
    LDM = 4
    STM = 5
    NOP = 14
    HALT = 15
    reg = [0] * 8
    mem = [0] * 32

    def get_op(inst):
        return (inst & 0xF000) >> 12

    def get_ri(inst):
        return (inst & 0x0F00) >> 8

    def get_val(inst):
        return (inst & 0x00FF)

    #pc = 0
    for inst in pipelined(program):
        #inst = program[pc]
        op = get_op(inst)
        ri = get_ri(inst)
        val = get_val(inst)
        if op == MOV:
            reg[ri] = val
        elif op == ADD:
            reg[ri] = reg[ri] + reg[val]
        elif op == SUB:
            reg[ri] = reg[ri] - reg[val]
        elif op == MUL:
            reg[ri] = reg[ri] * reg[val]
        elif op == LDM:
            reg[ri] = mem[val]
        elif op == STM:
            mem[val] = reg[ri]
        elif op == NOP:
            pass
        elif op == HALT:
            pass
        #pc += 1
    return reg[0]


@testbench
def test():
    # a + b + c
    a = 0x11
    b = 0x22
    c = 0x33
    program1 = [0x0000 + a,  # MOV r0 a
                0x5010,  # STM r0 [16]
                0x0100 + b,  # MOV r1 b
                0x5111,  # STM r1 [17]
                0x0200 + c,  # MOV r2 c
                0x5212,  # STM r2 [18]
                0x4310,  # LDM r3 [16]
                0x4411,  # LDM r4 [17]
                0x4512,  # LDM r5 [18]
                0x1304,  # ADD r3 r4
                0x1305,  # ADD r3 r5
                0x5300,  # STM r3 [0]
                #0xE000,  # NOP
                0x4000,  # LDM r0 [0]
                0xFF00]  # HALT
    ret = minivm(program1)
    print(ret)
    assert a + b + c == ret


if __name__ == '__main__':
    test()
