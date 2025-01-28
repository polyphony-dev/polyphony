from polyphony import testbench

def minivm(start_addr):
    LOAD0 = 0
    LOAD1 = 1
    ADD = 2
    SUB = 3
    MUL = 4
    HALT = 0xFF
    pc = start_addr
    reg = [0]*8
    program = [0x0001, 0x0102, 0x0200, 0x0103, 0x0200, 0xFF00, #1+2+3
               0x0002, 0x0103, 0x0400, 0x0104, 0x0400, 0xFF00] #2*3*4

    def get_op(inst):
        return (inst & 0xFF00) >> 8

    def get_v1(inst):
        return (inst & 0x00FF)

    while True:
        inst = program[pc]
        op = get_op(inst)
        print(op)
        v1 = get_v1(inst)
        if op == LOAD0:
            reg[0] = v1
        elif op == LOAD1:
            reg[1] = v1
        elif op == ADD:
            reg[0] = reg[0] + reg[1]
        elif op == SUB:
            reg[0] = reg[0] - reg[1]
        elif op == MUL:
            reg[0] = reg[0] * reg[1]
        elif op == HALT:
            break
        pc += 1
    return reg[0]

@testbench
def test():
    assert minivm(0) == 6
    assert minivm(6) == 24
