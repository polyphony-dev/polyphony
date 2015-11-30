#
#  FIR with 32 inputs, 32bit, 16 taps
#  NOTE: To change INPUTSIZE and TAPS, uncomment the other FIRFilterStreaming function
#  and comment out the current one. Currently, a loop has been unrolled for better performance.

#include <stdio.h>

from polyphony import testbench

def fir_filter_streaming(input:int, coeff:list, previous:list) -> int:
    INPUTSIZE=32
    TAPS=16
    EXPECTED_TOTAL=44880

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

    if previous[TAPS-1] == 0:
        return 0
    else:
        for j in range(TAPS):
            temp += previous[TAPS - j - 1] * coeff[j]

        return temp

"""
def fir_filter_streaming(in: int, coeff: list, previous: list) -> int:
    for j in range(TAPS-1, 0, -1):
        previous[j] = previous[j-1]
    previous[0] = in

    if previous[TAPS-1] == 0:
        return 0
    else:
        temp = 0
        for j in range(TAPS):
            temp += previous[TAPS - j - 1] * coeff[j]
        return temp
"""

def fir():
    INPUTSIZE=32
    TAPS=16
    EXPECTED_TOTAL=44880

    previous = [0] * 16
    coeff = [10] * 16
    output = [0] * 32
    total = 0
    for i in range(1, INPUTSIZE+1):
        output[i-1] = fir_filter_streaming(i, coeff, previous)
        total += output[i-1]

    print(total)
    if total == EXPECTED_TOTAL:
        print(111)
    else:
        print(100)
    return total

@testbench
def test():
    assert 44880 == fir()
test()
