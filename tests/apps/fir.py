#
#  FIR with 32 inputs, 32bit, 16 taps
#  NOTE: To change INPUTSIZE and TAPS, uncomment the other FIRFilterStreaming function
#  and comment out the current one. Currently, a loop has been unrolled for better performance.
from polyphony import testbench
from polyphony import unroll, pipelined


INPUTSIZE = 32
TAPS = 16
EXPECTED_TOTAL = 44880


def fir_filter_streaming_old(input:int, coeff:tuple, previous:list) -> int:
    temp = 0
    #UNROLLING THIS IMPROVES PERFROMANCE
    previous[15] = previous[14]
    previous[14] = previous[13]
    previous[13] = previous[12]
    previous[12] = previous[11]
    previous[11] = previous[10]
    previous[10] = previous[9]
    previous[9] = previous[8]
    previous[8] = previous[7]
    previous[7] = previous[6]
    previous[6] = previous[5]
    previous[5] = previous[4]
    previous[4] = previous[3]
    previous[3] = previous[2]
    previous[2] = previous[1]
    previous[1] = previous[0]
    previous[0] = input

    if previous[TAPS - 1] == 0:
        return 0
    else:
        for j in range(TAPS):
            temp += previous[TAPS - j - 1] * coeff[j]

        return temp


def fir_filter_streaming(input: int, coeff: tuple, previous: list) -> int:
    N = TAPS - 1
    for j in unroll(range(N)):
        jj = N - j
        previous[jj] = previous[jj - 1]
        #print(jj)
    previous[0] = input

    if previous[N] == 0:
        return 0
    else:
        temp = 0
        for j in pipelined(range(TAPS)):
            temp += previous[N - j] * coeff[j]
        return temp


coeff = (10,) * TAPS


def fir():
    previous = [0] * TAPS
    output = [0] * INPUTSIZE
    total = 0
    for i in range(1, INPUTSIZE + 1):
        output[i - 1] = fir_filter_streaming(i, coeff, previous)
        # output[i - 1] = fir_filter_streaming_old(i, coeff, previous)
        total += output[i - 1]

    return total


@testbench
def test():
    assert EXPECTED_TOTAL == fir()
