from polyphony import testbench
from polyphony import pipelined


def list32_a(buf0:list, buf1:list):
    ref0 = buf0
    ref1 = buf1
    for i in range(len(buf0)):
        ref0[i] = i + 1
        ref1[i] = (i + 1) * 2
        if i % 2 == 0:
           ref0 = buf1
           ref1 = buf0
        else:
           ref0 = buf0
           ref1 = buf1


def list32_b(buf0:list, buf1:list):
    ref0 = buf1  # dead code
    ref1 = buf0  # dead code
    for i in range(len(buf0)):
        if i % 2 == 0:
           ref0 = buf0
           ref1 = buf1
        else:
           ref0 = buf1
           ref1 = buf0
        ref0[i] = i + 1
        ref1[i] = (i + 1) * 2


def list32_c(buf0:list, buf1:list):
    ref0 = buf0
    ref1 = buf1
    for i in range(len(buf0)):
        ref0[i] = i + 1
        ref1[i] = (i + 1) * 2
        tmp = ref0
        ref0 = ref1
        ref1 = tmp


SIZE = 32
EXPECTED0 = [1, 4, 3, 8, 5, 12, 7, 16, 9, 20, 11, 24, 13, 28, 15, 32, 17, 36, 19, 40, 21, 44, 23, 48, 25, 52, 27, 56, 29, 60, 31, 64]
EXPECTED1 = [2, 2, 6, 4, 10, 6, 14, 8, 18, 10, 22, 12, 26, 14, 30, 16, 34, 18, 38, 20, 42, 22, 46, 24, 50, 26, 54, 28, 58, 30, 62, 32]


@testbench
def test_a():
    buf0 = [0] * SIZE
    buf1 = [0] * SIZE
    list32_a(buf0, buf1)
    for i in range(len(buf0)):
        assert EXPECTED0[i] == buf0[i]
    for i in range(len(buf1)):
        assert EXPECTED1[i] == buf1[i]


@testbench
def test_b():
    buf0 = [0] * SIZE
    buf1 = [0] * SIZE
    list32_b(buf0, buf1)
    for i in range(len(buf0)):
        assert EXPECTED0[i] == buf0[i]
    for i in range(len(buf1)):
        assert EXPECTED1[i] == buf1[i]


@testbench
def test_c():
    buf0 = [0] * SIZE
    buf1 = [0] * SIZE
    list32_c(buf0, buf1)
    for i in range(len(buf0)):
        assert EXPECTED0[i] == buf0[i]
    for i in range(len(buf1)):
        assert EXPECTED1[i] == buf1[i]


test_a()
test_b()
test_c()
