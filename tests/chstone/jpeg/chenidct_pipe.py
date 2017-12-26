from polyphony import testbench
from polyphony import rule

'''
+--------------------------------------------------------------------------+
| CHStone : A suite of Benchmark Programs for C-based High-Level Synthesis |
| ======================================================================== |
|                                                                          |
| * Collected and Modified : Y. Hara, H. Tomiyama, S. Honda,               |
|                            H. Takada and K. Ishii                        |
|                            Nagoya University, Japan                      |
|                                                                          |
| * Remarks :                                                              |
|    1. This source code is reformatted to follow CHStone's style.         |
|    2. Test vectors are added for CHStone.                                |
|    3. If "main_result" is 0 at the end of the program, the program is    |
|       successfully executed.                                             |
|    4. Follow the copyright of each benchmark program.                    |
+--------------------------------------------------------------------------+

/*
 *  IDCT transformation of Chen algorithm
 *
 *  @(#) $Id: chenidct.c,v 1.2 2003/07/18 10:19:21 honda Exp $
 */
/*************************************************************
Copyright (C) 1990, 1991, 1993 Andy C. Hung, all rights reserved.
PUBLIC DOMAIN LICENSE: Stanford University Portable Video Research
Group. If you use this software, you agree to the following: This
program package is purely experimental, and is licensed "as is".
Permission is granted to use, modify, and distribute this program
without charge for any purpose, provided this license/ disclaimer
notice appears in the copies.  No warranty or maintenance is given,
either expressed or implied.  In no event shall the author(s) be
liable to you or a third party for any special, incidental,
consequential, or other damages, arising out of the use or inability
to use the program for any purpose (or the loss of data), even if we
have been advised of such possibilities.  Any public reference or
advertisement of this source code should refer to it as the Portable
Video Research Group (PVRG) code, and not by any author(s) (or
Stanford University) name.
*************************************************************/
/*
************************************************************
chendct.c

A simple DCT algorithm that seems to have fairly nice arithmetic
properties.

W. H. Chen, C. H. Smith and S. C. Fralick "A fast computational
algorithm for the discrete cosine transform," IEEE Trans. Commun.,
vol. COM-25, pp. 1004-1009, Sept 1977.

************************************************************
'''

# Cos constants
c1d4 = 362
c1d8 = 473
c3d8 = 196
c1d16 = 502
c3d16 = 426
c5d16 = 284
c7d16 = 100

# NOTE: you must modify env.internal_ram_threshold_size > 32*64


def ChenIDct(x:list, y:list):
    '''
    ChenIDCT() implements the Chen inverse dct. Note that there are two
    input vectors that represent x=input, and y=output, and must be
    defined (and storage allocated) before this routine is called.
    '''
    def LS(r,s):
        return r << s

    def RS(r,s):
        return r >> s  # Caution with rounding...

    def MSCALE(expr):
        return RS(expr, 9)
    
    tmp = [None] * 64
    # Loop over columns
    with rule(scheduling='pipeline'):
        for i in range(8):
            b0 = LS(x[i + 0], 2)
            a0 = LS(x[i + 8], 2)
            b2 = LS(x[i + 16], 2)
            a1 = LS(x[i + 24], 2)
            b1 = LS(x[i + 32], 2)
            a2 = LS(x[i + 40], 2)
            b3 = LS(x[i + 48], 2)
            a3 = LS(x[i + 56], 2)

            # Split into even mode  b0 = x0  b1 = x4  b2 = x2  b3 = x6.
            # And the odd terms a0 = x1 a1 = x3 a2 = x5 a3 = x7.
            c0 = MSCALE((c7d16 * a0) - (c1d16 * a3))
            c1 = MSCALE((c3d16 * a2) - (c5d16 * a1))
            c2 = MSCALE((c3d16 * a1) + (c5d16 * a2))
            c3 = MSCALE((c1d16 * a0) + (c7d16 * a3))

            # First Butterfly on even terms.
            a0 = MSCALE(c1d4 * (b0 + b1))
            a1 = MSCALE(c1d4 * (b0 - b1))

            a2 = MSCALE((c3d8 * b2) - (c1d8 * b3))
            a3 = MSCALE((c1d8 * b2) + (c3d8 * b3))

            b0 = a0 + a3
            b1 = a1 + a2
            b2 = a1 - a2
            b3 = a0 - a3

            # Second Butterfly
            a0 = c0 + c1
            a1 = c0 - c1
            a2 = c3 - c2
            a3 = c3 + c2

            c0 = a0
            c1 = MSCALE(c1d4 * (a2 - a1))
            c2 = MSCALE(c1d4 * (a2 + a1))
            c3 = a3

            tmp[i + 0] = b0 + c3
            tmp[i + 8] = b1 + c2
            tmp[i + 16] = b2 + c1
            tmp[i + 24] = b3 + c0
            tmp[i + 32] = b3 - c0
            tmp[i + 40] = b2 - c1
            tmp[i + 48] = b1 - c2
            tmp[i + 56] = b0 - c3

        # Loop over rows
        for i in range(8):
            idx = LS(i, 3)
            b0 = tmp[idx + 0]
            a0 = tmp[idx + 1]
            b2 = tmp[idx + 2]
            a1 = tmp[idx + 3]
            b1 = tmp[idx + 4]
            a2 = tmp[idx + 5]
            b3 = tmp[idx + 6]
            a3 = tmp[idx + 7]

            # Split into even mode  b0 = x0  b1 = x4  b2 = x2  b3 = x6.
            # And the odd terms a0 = x1 a1 = x3 a2 = x5 a3 = x7.
            c0 = MSCALE((c7d16 * a0) - (c1d16 * a3))
            c1 = MSCALE((c3d16 * a2) - (c5d16 * a1))
            c2 = MSCALE((c3d16 * a1) + (c5d16 * a2))
            c3 = MSCALE((c1d16 * a0) + (c7d16 * a3))

            # First Butterfly on even terms.
            a0 = MSCALE(c1d4 * (b0 + b1))
            a1 = MSCALE(c1d4 * (b0 - b1))

            a2 = MSCALE((c3d8 * b2) - (c1d8 * b3))
            a3 = MSCALE((c1d8 * b2) + (c3d8 * b3))

            # Calculate last set of b's
            b0 = a0 + a3
            b1 = a1 + a2
            b2 = a1 - a2
            b3 = a0 - a3

            # Second Butterfly
            a0 = c0 + c1
            a1 = c0 - c1
            a2 = c3 - c2
            a3 = c3 + c2

            c0 = a0
            c1 = MSCALE(c1d4 * (a2 - a1))
            c2 = MSCALE(c1d4 * (a2 + a1))
            c3 = a3

            idx = LS(i, 3)
            tmp[idx + 0] = b0 + c3
            tmp[idx + 1] = b1 + c2
            tmp[idx + 2] = b2 + c1
            tmp[idx + 3] = b3 + c0
            tmp[idx + 4] = b3 - c0
            tmp[idx + 5] = b2 - c1
            tmp[idx + 6] = b1 - c2
            tmp[idx + 7] = b0 - c3

        # Retrieve correct accuracy. We have additional factor
        # of 16 that must be removed.
        for i in range(64):
            v = tmp[i]
            if v < 0:
                z = (v - 8) >> 4
            else:
                z = (v + 8) >> 4
            y[i] = z
    return 0


@testbench
def test():
    ins = [
        154, 192, 254, 239, 180, 128, 123, 110,
        123, 180, 198, 180, 154, 136, 105, 136,
        123, 136, 154, 136, 136, 123, 110, 123,
        123, 154, 154, 180, 167, 136, 149, 123,
        123, 154, 180, 180, 166, 154, 136, 123,
        123, 154, 154, 166, 149, 180, 136, 136,
        123, 136, 123, 123, 136, 198, 180, 154,
        136, 110, 123, 123, 136, 154, 166, 136
    ]
    outs = [0] * 64

    expected = [
        1077, -250,  114, -109,  76, -27,  56,  12,
        -232,  156, -106,  -16, -13,  -9, -25,   8,
        236,  -74,   62,  -20,   5,  -4,  31,   6,
        16,   48,  -68,  -18, -18,  -7,   1, -16,
        163,  -30,   -7,  -25,  16,  23,  -9,  22,
        29,   -9,   -4,   -4,  -4,  13, -13,  -8,
        81,   -2,  -12,  -10,  12,  15,   5,  11,
        37,    3,   -4,   -7,  -6,   6,   7,  18
    ]

    ChenIDct(ins, outs)

    for i in range(64):
        print(outs[i])
        assert outs[i] == expected[i]


test()
