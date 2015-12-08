import profile
from polyphony import testbench

#
#+--------------------------------------------------------------------------+
#| * Test Vectors (added for CHStone)                                       |
#|     A : input data                                                       |
#|     outData : expected output data                                       |
#+--------------------------------------------------------------------------+
#

R = 0
ADDU = 33
SUBU = 35
MULT = 24
MULTU = 25
MFHI = 16
MFLO = 18
AND = 36
OR = 37
XOR = 38
SLL = 0
SRL = 2
SLLV = 4
SRLV = 6
SLT = 42
SLTU = 43
JR = 8
J = 2
JAL = 3
ADDIU = 9
ANDI = 12
ORI = 13
XORI = 14
LW = 35
SW = 43
LUI = 15
BEQ = 4
BNE = 5
BGEZ = 1
SLTI = 10
SLTIU = 11

def mips_main(imem:list, dmem:list):
    def IADDR(x):
        return (((x)&0x000000ff)>>2)

    def DADDR(x):
        return (((x)&0x000000ff)>>2)

    n_inst = 0

    reg = [0]*32
    reg[29] = 0x7fffeffc

    pc = 0x00400000

    while True:
        iaddr = IADDR(pc)
        ins = imem[iaddr]
        pc = pc + 4
        op = ins >> 26
        if op == R:
            funct = ins & 0x3f
            shamt = (ins >> 6) & 0x1f
            rd = (ins >> 11) & 0x1f
            rt = (ins >> 16) & 0x1f
            rs = (ins >> 21) & 0x1f

            if funct == ADDU:
                reg[rd] = reg[rs] + reg[rt]
            elif funct == SUBU:
                reg[rd] = reg[rs] - reg[rt]

            #elif funct == MULT:
            #    hilo = reg[rs] * reg[rt]
            #    Lo = hilo & 0x00000000ffffffff
            #    Hi = (hilo >> 32) & 0xffffffff
            #
            #elif funct == MULTU:
            #    hilo = reg[rs] * reg[rt]
            #    Lo = hilo & 0x00000000ffffffff
            #    Hi = (hilo >> 32) & 0xffffffff
            #
            #elif funct == MFHI:
            #    reg[rd] = Hi
            #
            #elif funct == MFLO:
            #    reg[rd] = Lo

            elif funct == AND:
                reg[rd] = reg[rs] & reg[rt]

            elif funct == OR:
                reg[rd] = reg[rs] | reg[rt]

            elif funct == XOR:
                reg[rd] = reg[rs] ^ reg[rt]

            elif funct == SLL:
                reg[rd] = reg[rt] << shamt

            elif funct == SRL:
                reg[rd] = reg[rt] >> shamt

            elif funct == SLLV:
                reg[rd] = reg[rt] << reg[rs]

            elif funct == SRLV:
                reg[rd] = reg[rt] >> reg[rs]

            elif funct == SLT:
                reg[rd] = reg[rs] < reg[rt]

            elif funct == SLTU:
                reg[rd] = reg[rs] < reg[rt]

            elif funct == JR:
                pc = reg[rs]

            else:
                pc = 0 # error

        elif op == J:
            tgtadr = ins & 0x3ffffff
            pc = tgtadr << 2

        elif op == JAL:
            tgtadr = ins & 0x3ffffff
            reg[31] = pc
            pc = tgtadr << 2

        else:# if op == ...

            address = ins & 0xffff
            rt = (ins >> 16) & 0x1f
            rs = (ins >> 21) & 0x1f
            if op == ADDIU:
                reg[rt] = reg[rs] + address

            elif op == ANDI:
                reg[rt] = reg[rs] & address

            elif op == ORI:
                reg[rt] = reg[rs] | address

            elif op == XORI:
                reg[rt] = reg[rs] ^ address

            elif op == LW:
                daddr = DADDR (reg[rs] + address)
                reg[rt] = dmem[daddr]
                
            elif op == SW:
                dmem[DADDR (reg[rs] + address)] = reg[rt]

            elif op == LUI:
                reg[rt] = address << 16

            elif op == BEQ:
                if reg[rs] == reg[rt]:
                    pc = pc - 4 + (address << 2)
            elif op == BNE:
                if reg[rs] != reg[rt]:
                    pc = pc - 4 + (address << 2)

            elif op == BGEZ:
                if reg[rs] >= 0:
                    pc = pc - 4 + (address << 2)

            elif op == SLTI:
                reg[rt] = reg[rs] < address

            elif op == SLTIU:
                reg[rt] = reg[rs] < address

            else:
                pc = 0; # error

        reg[0] = 0
        n_inst += 1
        if pc == 0:
            break

    return n_inst

@testbench
def test():
    imem = [
        0x8fa40000,	# [0x00400000]  lw $4, 0($29)       ; 175: lw $a0 0($sp)    # argc
        0x27a50004,	# [0x00400004]  addiu $5, $29, 4    ; 176: addiu $a1 $sp 4  # argv
        0x24a60004,	# [0x00400008]  addiu $6, $5, 4     ; 177: addiu $a2 $a1 4  # envp
        0x00041080,	# [0x0040000c]  sll $2, $4, 2       ; 178: sll $v0 $a0 2
        0x00c23021,	# [0x00400010]  addu $6, $6, $2     ; 179: addu $a2 $a2 $v0
        0x0c100016,	# [0x00400014]  jal 0x00400058 [main] ; 180: jal main
        0x00000000,	# [0x00400018]  nop                   ; 181: nop
        0x3402000a,	# [0x0040001c]  ori $2, $0, 10        ; 183: li $v0 10
        0x0000000c,	# [0x00400020]  syscall               ; 184: syscall  # syscall 10 (exit)
        0x3c011001,	# [0x00400024]  lui $1, 4097 [A]      ; 4: la   $t0,A           ; C&S
        0x34280000,	# [0x00400028]  ori $8, $1, 0 [A]
        0x00044880,	# [0x0040002c]  sll $9, $4, 2                   ; 5: sll  $t1,$a0,2
        0x01094821,	# [0x00400030]  addu $9, $8, $9                 ; 6: addu $t1,$t0,$t1
        0x8d2a0000,	# [0x00400034]  lw $10, 0($9)                   ; 7: lw   $t2,($t1)
        0x00055880,	# [0x00400038]  sll $11, $5, 2                  ; 8: sll  $t3,$a1,2
        0x010b5821,	# [0x0040003c]  addu $11, $8, $11               ; 9: addu $t3,$t0,$t3
        0x8d6c0000,	# [0x00400040]  lw $12, 0($11)                  ; 10: lw   $t4,($t3)
        0x018a682a,	# [0x00400044]  slt $13, $12, $10               ; 11: slt  $t5,$t4,$t2
        0x11a00003,	# [0x00400048]  beq $13, $0, 12 [L1-0x00400048] ; 12: beq  $t5,$zero,L1
        0xad2c0000,	# [0x0040004c]  sw $12, 0($9)                   ; 13: sw   $t4,($t1)
        0xad6a0000,	# [0x00400050]  sw $10, 0($11)                  ; 14: sw   $t2,($t3)
        0x03e00008,	# [0x00400054]  jr $31                          ; 15: jr   $ra            ; L1
        0x27bdfff4,	# [0x00400058]  addiu $29, $29, -12             ; 17: addiu $sp,$sp,-12   ; main
        0xafbf0008,	# [0x0040005c]  sw $31, 8($29)                  ; 18: sw   $ra,8($sp)
        0xafb10004,	# [0x00400060]  sw $17, 4($29)                  ; 19: sw   $s1,4($sp)
        0xafb00000,	# [0x00400064]  sw $16, 0($29)                  ; 20: sw   $s0,0($sp)
        0x24100000,	# [0x00400068]  addiu $16, $0, 0                ; 21: addiu $s0,$zero,0
        0x2a080008,	# [0x0040006c]  slti $8, $16, 8                 ; 22: slti $t0,$s0,8      ; L5
        0x1100000b,	# [0x00400070]  beq $8, $0, 44 [L2-0x00400070]  ; 23: beq  $t0,$zero,L2
        0x26110001,	# [0x00400074]  addiu $17, $16, 1               ; 24: addiu $s1,$s0,1
        0x2a280008,	# [0x00400078]  slti $8, $17, 8                 ; 25: slti $t0,$s1,8      ; L4
        0x11000006,	# [0x0040007c]  beq $8, $0, 24 [L3-0x0040007c]  ; 26: beq  $t0,$zero,L3
        0x26040000,	# [0x00400080]  addiu $4, $16, 0                ; 27: addiu $a0,$s0,0
        0x26250000,	# [0x00400084]  addiu $5, $17, 0                ; 28: addiu $a1,$s1,0
        0x0c100009,	# [0x00400088]  jal 0x00400024 [compare_swap]   ; 29: jal  compare_swap
        0x26310001,	# [0x0040008c]  addiu $17, $17, 1               ; 30: addiu $s1,$s1,1
        0x0810001e,	# [0x00400090]  j 0x00400078 [L4]               ; 31: j    L4
        0x26100001,	# [0x00400094]  addiu $16, $16, 1               ; 32: addiu $s0,$s0,1     ; L3
        0x0810001b,	# [0x00400098]  j 0x0040006c [L5]               ; 33: j    L5
        0x8fbf0008,	# [0x0040009c]  lw $31, 8($29)                  ; 34: lw   $ra,8($sp)     ; L2
        0x8fb10004,	# [0x004000a0]  lw $17, 4($29)                  ; 35: lw   $s1,4($sp)
        0x8fb00000,	# [0x004000a4]  lw $16, 0($29)                  ; 36: lw   $s0,0($sp)
        0x27bd000c,	# [0x004000a8]  addiu $29, $29, 12              ; 37: addiu $sp,$sp,12
        0x03e00008,	# [0x004000ac]  jr $31                          ; 38: jr   $ra
    ]

    inputs = [ 22, 5, -9, 3, -17, 38, 0, 11 ]
    dmem = [0] * 64
    for i in range(8):
        dmem[i] = inputs[i]

    main_result = 611 != mips_main(imem, dmem)
    for i in range(0, 8):
        print(dmem[i])
    for i in range(1, 8):
        main_result += dmem[i-1] > dmem[i]
    assert main_result == 0

test()
