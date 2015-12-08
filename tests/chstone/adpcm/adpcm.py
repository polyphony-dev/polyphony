# +--------------------------------------------------------------------------+
# | CHStone : a suite of benchmark programs for C-based High-Level Synthesis |
# | ======================================================================== |
# |                                                                          |
# | * Collected and Modified : Y. Hara, H. Tomiyama, S. Honda,               |
# |                            H. Takada and K. Ishii                        |
# |                            Nagoya University, Japan                      |
# |                                                                          |
# | * Remark :                                                               |
# |    1. This source code is modified to unify the formats of the benchmark |
# |       programs in CHStone.                                               |
# |    2. Test vectors are added for CHStone.                                |
# |    3. If "main_result" is 0 at the end of the program, the program is    |
# |       correctly executed.                                                |
# |    4. Please follow the copyright of each benchmark program.             |
# +--------------------------------------------------------------------------+
# */
# /*************************************************************************/
# /*                                                                       */
# /*   SNU-RT Benchmark Suite for Worst Case Timing Analysis               */
# /*   =====================================================               */
# /*                              Collected and Modified by S.-S. Lim      */
# /*                                           sslim@archi.snu.ac.kr       */
# /*                                         Real-Time Research Group      */
# /*                                        Seoul National University      */
# /*                                                                       */
# /*                                                                       */
# /*        < Features > - restrictions for our experimental environment   */
# /*                                                                       */
# /*          1. Completely structured.                                    */
# /*               - There are no unconditional jumps.                     */
# /*               - There are no exit from loop bodies.                   */
# /*                 (There are no 'break' or 'return' in loop bodies)     */
# /*          2. No 'switch' statements.                                   */
# /*          3. No 'do..while' statements.                                */
# /*          4. Expressions are restricted.                               */
# /*               - There are no multiple expressions joined by 'or',     */
# /*                'and' operations.                                      */
# /*          5. No library calls.                                         */
# /*               - All the functions needed are implemented in the       */
# /*                 source file.                                          */
# /*                                                                       */
# /*                                                                       */
# /*************************************************************************/
# /*                                                                       */
# /*  FILE: adpcm.c                                                        */
# /*  SOURCE : C Algorithms for Real-Time DSP by P. M. Embree              */
# /*                                                                       */
# /*  DESCRIPTION :                                                        */
# /*                                                                       */
# /*     CCITT G.722 ADPCM (Adaptive Differential Pulse Code Modulation)   */
# /*     algorithm.                                                        */
# /*     16khz sample rate data is stored in the array test_data[SIZE].    */
# /*     Results are stored in the array compressed[SIZE] and result[SIZE].*/
# /*     Execution time is determined by the constant SIZE (default value  */
# /*     is 2000).                                                         */
# /*                                                                       */
# /*  REMARK :                                                             */
# /*                                                                       */
# /*  EXECUTION TIME :                                                     */
# /*                                                                       */
# /*                                                                       */
# /*************************************************************************/

# G722 C code

# variables for transimit quadrature mirror filter here
tqmf = [0] * 24

# QMF filter coefficients:
# scaled by a factor of 4 compared to G722 CCITT recomendation
h = [
      12,   -44,  -44,   212,    48, -624,   128, 1448,
    -840, -3220, 3804, 15504, 15504, 3804, -3220, -840,
    1448,   128, -624,    48,   212,  -44,   -44,   12
]

xl = 0
xh = 0

# variables for receive quadrature mirror filter here
accumc= [0] * 11
accumd= [0] * 11

# outputs of decode()
xout1 = 0
xout2 = 0

xs = 0
xd = 0

# variables for encoder (hi and lo) here
il = 0
szl = 0
spl = 0
sl = 0
el = 0

qq4_code4_table = [
        0, -20456, -12896, -8968, -6288, -4240, -2584, -1200,
    20456,  12896,   8968,  6288,  4240,  2584,  1200,     0
]


qq6_code6_table = [
      -136,   -136,   -136,   -136, -24808, -21904, -19008, -16704,
    -14984, -13512, -12280, -11192, -10232,  -9360,  -8576,  -7856,
     -7192,  -6576,  -6000,  -5456,  -4944,  -4464,  -4008,  -3576,
     -3168,  -2776,  -2400,  -2032,  -1688,  -1360,  -1040,   -728,
     24808,  21904,  19008,  16704,  14984,  13512,  12280,  11192,
     10232,   9360,   8576,   7856,   7192,   6576,   6000,   5456,
      4944,   4464,   4008,   3576,   3168,   2776,   2400,   2032,
      1688,   1360,   1040,    728,    432,    136,   -432,   -136
]

delay_bpl = [0] * 6

delay_dltx = [0] * 6

wl_code_table = [
     -60, 3042, 1198, 538, 334, 172,  58, -30,
    3042, 1198, 538,  334, 172,  58, -30, -60
]

ilb_table = [
    2048, 2093, 2139, 2186, 2233, 2282, 2332, 2383,
    2435, 2489, 2543, 2599, 2656, 2714, 2774, 2834,
    2896, 2960, 3025, 3091, 3158, 3228, 3298, 3371,
    3444, 3520, 3597, 3676, 3756, 3838, 3922, 4008
]

nbl = 0			# delay line
al1 = 0
al2 = 0
plt = 0
plt1 = 0
plt2 = 0
dlt = 0
rlt = 0
rlt1 = 0
rlt2 = 0

# decision levels - pre-multiplied by 8, 0 to indicate end
decis_levl = [
      280,   576,   880,  1200,  1520,  1864,  2208,  2584,
     2960,  3376,  3784,  4240,  4696,  5200,  5712,  6288,
     6864,  7520,  8184,  8968,  9752, 10712, 11664, 12896,
    14120, 15840, 17560, 20456, 23352, 32767
]

detl = 32

# quantization table 31 long to make quantl look-up easier,
# last entry is for mil=30 case when wd is max
quant26bt_pos = [
    61, 60, 59, 58, 57, 56, 55, 54,
    53, 52, 51, 50, 49, 48, 47, 46,
    45, 44, 43, 42, 41, 40, 39, 38,
    37, 36, 35, 34, 33, 32, 32
]

# quantization table 31 long to make quantl look-up easier,
# last entry is for mil=30 case when wd is max
quant26bt_neg = [
    63, 62, 31, 30, 29, 28, 27, 26,
    25, 24, 23, 22, 21, 20, 19, 18,
    17, 16, 15, 14, 13, 12, 11, 10,
     9,  8,  7,  6,  5,  4, 4
]


deth = 8
sh = 0   # this comes from adaptive predictor
eh = 0

qq2_code2_table = [
    -7408, -1616, 7408, 1616
]

wh_code_table = [
    798, -214, 798, -214
]


dh = 0
ih = 0
nbh = 0
szh = 0
sph = 0
ph = 0
yh = 0
rh = 0

delay_dhx = [0] * 6

delay_bph = [0] * 6

ah1 = 0
ah2 = 0
ph1 = 0
ph2 = 0
rh1 = 0
rh2 = 0

# variables for decoder here
ilr = 0
rl = 0
dec_deth = 8
dec_detl = 32
dec_dlt = 0

dec_del_bpl = [0] * 6

dec_del_dltx = [0] * 6

dec_plt = 0
dec_plt1 = 0
dec_plt2 = 0
dec_szl = 0
dec_spl = 0
dec_sl = 0
dec_rlt1 = 0
dec_rlt2 = 0
dec_rlt = 0
dec_al1 = 0
dec_al2 = 0
dl = 0
dec_nbl = 0
dec_dh = 0
dec_nbh = 0

# variables used in filtez
dec_del_bph = [0] * 6

dec_del_dhx = [0] * 6

dec_szh = 0
# variables used in filtep
dec_rh1 = 0
dec_rh2 = 0
dec_ah1 = 0
dec_ah2 = 0
dec_ph = 0
dec_sph = 0

dec_sh = 0

dec_ph1 = 0
dec_ph2 = 0

# G722 encode function two ints in, one 8 bit output

# put input samples in xin1 = first value, xin2 = second value
# returns il and ih stored together

def abs(n) -> int:
    if n >= 0:
        m = n
    else:
        m = -n
    return m


def encode(xin1, xin2) -> int:
    # main multiply accumulate loop for samples and coefficients
    xa = 0
    xb = 0
    for i in range(0, 24, 2):
        xa += tqmf[i] * h[i]
        xb += tqmf[i+1] * h[i+1]

    # update delay line tqmf
    for i in range(23, 1, -1):
        tqmf[i] = tqmf[i-2]        
    tqmf[1] = xin1
    tqmf[0] = xin2


    # scale outputs
    global xl, xh
    xl = (xa + xb) >> 15
    xh = (xa - xb) >> 15

    # end of quadrature mirror filter code

    # starting with lower sub band encoder

    # filtez - compute predictor output section - zero section
    global szl
    szl = filtez(delay_bpl, delay_dltx)

    global spl, rlt1, al1, rlt2, al2
    # filtep - compute predictor output signal (pole section)
    spl = filtep (rlt1, al1, rlt2, al2)

    # compute the predictor output value in the lower sub_band encoder
    global sl, el
    sl = szl + spl
    el = xl - sl

    # quantl: quantize the difference signal
    global detl, il
    il = quantl (el, detl)

    # computes quantized difference signal
    # for invqbl, truncate by 2 lsbs, so mode = 3
    global dlt
    dlt = (detl * qq4_code4_table[il >> 2]) >> 15

    # logscl: updates logarithmic quant. scale factor in low sub band
    global nbl
    nbl = logscl(il, nbl)

    # scalel: compute the quantizer scale factor in the lower sub band
    # calling parameters nbl and 8 (constant such that scalel can be scaleh)
    global detl
    detl = scalel(nbl, 8)

    # parrec - simple addition to compute recontructed signal for adaptive pred
    global plt
    plt = dlt + szl

    # upzero: update zero section predictor coefficients (sixth order)
    # calling parameters: dlt, dlt1, dlt2, ..., dlt6 from dlt
    #  bpli (linear_buffer in which all six values are delayed
    # return params:      updated bpli, delayed dltx
    upzero(dlt, delay_dltx, delay_bpl)

    # uppol2- update second predictor coefficient apl2 and delay it as al2
    # calling parameters: al1, al2, plt, plt1, plt2
    global al1, al2, plt1, plt2
    al2 = uppol2(al1, al2, plt, plt1, plt2)

    # uppol1 :update first predictor coefficient apl1 and delay it as al1
    # calling parameters: al1, apl2, plt, plt1
    
    al1 = uppol1(al1, al2, plt, plt1)

    # recons : compute recontructed signal for adaptive predictor
    rlt = sl + dlt

    # done with lower sub_band encoder; now implement delays for next time
    rlt2 = rlt1
    rlt1 = rlt
    plt2 = plt1
    plt1 = plt

    # high band encode
    global szh
    szh = filtez(delay_bph, delay_dhx)
    global sph, rh1, rh2, ah1, ah2
    sph = filtep(rh1, ah1, rh2, ah2)

    # predic: sh = sph + szh
    sh = sph + szh
    # subtra: eh = xh - sh
    eh = xh - sh

    # quanth - quantization of difference signal for higher sub-band
    # quanth: in-place for speed params: eh, deth (has init. value)
    if eh >= 0:
        ih = 3			# 2,3 are pos codes
    else:
        ih = 1			# 0,1 are neg codes
    global deth
    decis = (564 * deth) >> 12
    if abs(eh) > decis:
        ih -= 1			# mih = 2 case

    # compute the quantized difference signal, higher sub-band
    dh = (deth * qq2_code2_table[ih]) >> 15

    # logsch: update logarithmic quantizer scale factor in hi sub-band
    global nbh
    nbh = logsch(ih, nbh)

    # note : scalel and scaleh use same code, different parameters
    deth = scalel(nbh, 10)

    # parrec - add pole predictor output to quantized diff. signal
    ph = dh + szh

    # upzero: update zero section predictor coefficients (sixth order)
    # calling parameters: dh, dhi, bphi
    # return params: updated bphi, delayed dhx
    upzero(dh, delay_dhx, delay_bph)

    # uppol2: update second predictor coef aph2 and delay as ah2
    # calling params: ah1, ah2, ph, ph1, ph2
    global ph1, ph2
    ah2 = uppol2(ah1, ah2, ph, ph1, ph2)

    # uppol1:  update first predictor coef. aph2 and delay it as ah1
    ah1 = uppol1(ah1, ah2, ph, ph1)

    # recons for higher sub-band
    yh = sh + dh

    # done with higher sub-band encoder, now Delay for next time
    rh2 = rh1
    rh1 = yh
    ph2 = ph1
    ph1 = ph

    # multiplex ih and il to get signals together
    return il | (ih << 6)


# decode function, result in xout1 and xout2
def decode(input):
    # split transmitted word from input into ilr and ih
    ilr = input & 0x3f
    ih = input >> 6

    # LOWER SUB_BAND DECODER

    # filtez: compute predictor output for zero section
    dec_szl = filtez (dec_del_bpl, dec_del_dltx)

    # filtep: compute predictor output signal for pole section
    global dec_rlt1, dec_al1, dec_rlt2, dec_al2
    dec_spl = filtep (dec_rlt1, dec_al1, dec_rlt2, dec_al2)

    dec_sl = dec_spl + dec_szl

    # compute quantized difference signal for adaptive predic
    global dec_detl
    dec_dlt = (dec_detl * qq4_code4_table[ilr >> 2]) >> 15

    # compute quantized difference signal for decoder output
    dl = (dec_detl * qq6_code6_table[il]) >> 15

    rl = dl + dec_sl

    # logscl: quantizer scale factor adaptation in the lower sub-band
    global dec_nbl
    dec_nbl = logscl(ilr, dec_nbl)

    # scalel: computes quantizer scale factor in the lower sub band
    dec_detl = scalel(dec_nbl, 8)

    # parrec - add pole predictor output to quantized diff. signal
    # for partially reconstructed signal
    dec_plt = dec_dlt + dec_szl

    # upzero: update zero section predictor coefficients
    upzero(dec_dlt, dec_del_dltx, dec_del_bpl)

    # uppol2: update second predictor coefficient apl2 and delay it as al2
    global dec_plt1, dec_plt2
    dec_al2 = uppol2(dec_al1, dec_al2, dec_plt, dec_plt1, dec_plt2)

    # uppol1: update first predictor coef. (pole setion)
    dec_al1 = uppol1(dec_al1, dec_al2, dec_plt, dec_plt1)
    
    # recons : compute recontructed signal for adaptive predictor
    dec_rlt = dec_sl + dec_dlt

    # done with lower sub band decoder, implement delays for next time
    dec_rlt2 = dec_rlt1
    dec_rlt1 = dec_rlt
    dec_plt2 = dec_plt1
    dec_plt1 = dec_plt

    # HIGH SUB-BAND DECODER

    # filtez: compute predictor output for zero section
    dec_szh = filtez (dec_del_bph, dec_del_dhx)

    # filtep: compute predictor output signal for pole section
    global dec_rh1, dec_rh2, dec_ah1, dec_ah2
    dec_sph = filtep (dec_rh1, dec_ah1, dec_rh2, dec_ah2)

    # predic:compute the predictor output value in the higher sub_band decoder
    dec_sh = dec_sph + dec_szh

    # in-place compute the quantized difference signal
    global dec_deth
    dec_dh = (dec_deth * qq2_code2_table[ih]) >> 15

    # logsch: update logarithmic quantizer scale factor in hi sub band
    global dec_nbh
    dec_nbh = logsch(ih, dec_nbh)

    # scalel: compute the quantizer scale factor in the higher sub band
    dec_deth = scalel(dec_nbh, 10)

    # parrec: compute partially recontructed signal
    dec_ph = dec_dh + dec_szh

    # upzero: update zero section predictor coefficients
    upzero(dec_dh, dec_del_dhx, dec_del_bph)

    # uppol2: update second predictor coefficient aph2 and delay it as ah2
    global dec_ph1, dec_ph2
    dec_ah2 = uppol2(dec_ah1, dec_ah2, dec_ph, dec_ph1, dec_ph2)

    # uppol1: update first predictor coef. (pole setion)
    dec_ah1 = uppol1(dec_ah1, dec_ah2, dec_ph, dec_ph1)

    # recons : compute recontructed signal for adaptive predictor
    rh = dec_sh + dec_dh

    # done with high band decode, implementing delays for next time here
    dec_rh2 = dec_rh1
    dec_rh1 = rh
    dec_ph2 = dec_ph1
    dec_ph1 = dec_ph

    # end of higher sub_band decoder

    # end with receive quadrature mirror filters
    xd = rl - rh
    xs = rl + rh

    # receive quadrature mirror filters implemented here
    xa1 = xd * h[0]
    xa2 = xs * h[1]

    # main multiply accumulate loop for samples and coefficients
    for i in range(10):
        xa1 += accumc[i] * h[i*2+2]
        xa2 += accumd[i] * h[i*2+3]
    # final mult/accumulate
    xa1 += accumc[10] * h[22]
    xa2 += accumd[10] * h[23]

    # scale by 2^14
    global xout1, xout2
    xout1 = xa1 >> 14
    xout2 = xa2 >> 14

    #print('xout1', xout1)
    # update delay lines
    for i in range(10, 0, -1):
        accumc[i] = accumc[i-1]
        accumd[i] = accumd[i-1]        
      
    accumc[0] = xd
    accumd[0] = xs


# clear all storage locations
def reset():
    detl = dec_detl = 32		# reset to min scale factor
    deth = dec_deth = 8
    nbl = al1 = al2 = plt1 = plt2 = rlt1 = rlt2 = 0
    nbh = ah1 = ah2 = ph1 = ph2 = rh1 = rh2 = 0
    dec_nbl = dec_al1 = dec_al2 = dec_plt1 = dec_plt2 = dec_rlt1 = dec_rlt2 = 0
    dec_nbh = dec_ah1 = dec_ah2 = dec_ph1 = dec_ph2 = dec_rh1 = dec_rh2 = 0

    for i in range(6):
        delay_dltx[i] = 0
        delay_dhx[i] = 0
        dec_del_dltx[i] = 0
        dec_del_dhx[i] = 0

    for i in range(6):
        delay_bpl[i] = 0
        delay_bph[i] = 0
        dec_del_bpl[i] = 0
        dec_del_bph[i] = 0

    for i in range(24):
        tqmf[i] = 0		# i<23

    for i in range(11):
        accumc[i] = 0
        accumd[i] = 0
    
def dump():
    print('detl', detl)
    print('dec_detl', dec_detl)
    print('deth', deth)
    print('dec_deth', dec_deth)
    print('nbl', nbl)
    print('al1', al1)
    print('al2', al2)
    print('plt1', plt1)
    print('plt2', plt2)
    print('rlt1', rlt1)
    print('rlt2', rlt2)
    print('nbh', nbh)
    print('ah1', ah1)
    print('ah2', ah2)
    print('ph1', ph1)
    print('ph2', ph1)
    print('rh1', rh1)
    print('rh2', rh2)
    print('dec_nbl', dec_nbl)
    print('dec_al1', dec_al1)
    print('dec_al2', dec_al2)
    print('dec_plt1', dec_plt1)
    print('dec_plt2', dec_plt2)
    print('dec_rlt1', dec_rlt1)
    print('dec_rlt2', dec_rlt2)
    print('dec_nbh', dec_nbh)
    print('dec_ah1', dec_ah1)
    print('dec_ah2', dec_ah2)
    print('dec_ph1', dec_ph1)
    print('dec_ph2', dec_ph1)
    print('dec_rh1', dec_rh1)
    print('dec_rh2', dec_rh2)

# filtez - compute predictor output signal (zero section)
# input: bpl1-6 and dlt1-6, output: szl

def filtez (bpl:list, dlt:list) -> int:
    zl = 0
    for i in range(6):
        zl += bpl[i] * dlt[i]

    return (zl >> 14) # x2 here


# filtep - compute predictor output signal (pole section)
# input rlt1-2 and al1-2, output spl

def filtep (rlt1, al1, rlt2, al2) -> int:
    pl = 2 * rlt1
    pl = al1 * pl
    pl2 = 2 * rlt2
    pl += al2 * pl2
    return pl >> 15


# quantl - quantize the difference signal in the lower sub-band
def quantl(el, detl) -> int:
    # abs of difference signal
    wd = abs(el)
    # determine mil based on decision levels and detl gain
    for mil in range(30):
        decis = (decis_levl[mil] * detl) >> 15
        if wd <= decis:
            break
    
    # if mil=30 then wd is less than all decision levels
    if el >= 0:
        ril = quant26bt_pos[mil]
    else:
        ril = quant26bt_neg[mil]
    return ril


# logscl - update log quantizer scale factor in lower sub-band
# note that nbl is passed and returned
def logscl(il, nbl) -> int:
    wd = (nbl * 127) >> 7 # leak factor 127/128
    nbl = wd + wl_code_table[il >> 2]
    if nbl < 0:
        nbl = 0
    if nbl > 18432:
        nbl = 18432
    return nbl


# scalel: compute quantizer scale factor in lower or upper sub-band
def scalel (nbl, shift_constant) -> int:
    wd1 = (nbl >> 6) & 31
    wd2 = nbl >> 11
    wd3 = ilb_table[wd1] >> (shift_constant + 1 - wd2)
    return wd3 << 3


# upzero - inputs: dlt, dlti[0-5], bli[0-5], outputs: updated bli[0-5]
# also implements delay of bli and update of dlti from dlt
def upzero (dlt, dlti:list, bli:list) -> None:
    #if dlt is zero, then no sum into bli
    if dlt == 0:
        for i in range(6):
            bli[i] = ((255 * bli[i]) >> 8)	# leak factor of 255/256
    else:
        for i in range(6):
            if dlt * dlti[i] >= 0:
                wd2 = 128
            else:
                wd2 = -128
            wd3 = ((255 * bli[i]) >> 8)	# leak factor of 255/256
            bli[i] = wd2 + wd3

    # implement delay line for dlt
    dlti[5] = dlti[4]
    dlti[4] = dlti[3]
    dlti[3] = dlti[2]
    dlti[2] = dlti[1]
    dlti[1] = dlti[0]
    dlti[0] = dlt


# uppol2 - update second predictor coefficient (pole section)
# inputs: al1, al2, plt, plt1, plt2. outputs: apl2

def uppol2 (al1, al2, plt, plt1, plt2) -> int:
    wd2 = 4 * al1
    if plt * plt1 >= 0:
        wd2 = -wd2			# check same sign
    wd2 = wd2 >> 7		# gain of 1/128
    if plt * plt2 >= 0:
        wd4 = wd2 + 128		# same sign case
    else:
        wd4 = wd2 - 128
    apl2 = wd4 + (127 * al2 >> 7)	# leak factor of 127/128

    # apl2 is limited to +-.75
    if apl2 > 12288:
        apl2 = 12288
    if apl2 < -12288:
        apl2 = -12288
    return apl2


# uppol1 - update first predictor coefficient (pole section)
# inputs: al1, apl2, plt, plt1. outputs: apl1

def uppol1 (al1, apl2, plt, plt1) -> int:
    wd2 = (al1 * 255) >> 8	# leak factor of 255/256
    if plt * plt1 >= 0:
        apl1 = wd2 + 192	# same sign case
    else:
        apl1 = wd2 - 192

    # note: wd3= .9375-.75 is always positive
    wd3 = 15360 - apl2		# limit value
    if apl1 > wd3:
        apl1 = wd3
    if apl1 < -wd3:
        apl1 = -wd3
    return apl1


# logsch - update log quantizer scale factor in higher sub-band
# note that nbh is passed and returned
def logsch(ih, nbh) -> int:
    wd = (nbh * 127) >> 7	# leak factor 127/128
    nbh = wd + wh_code_table[ih]
    if nbh < 0:
        nbh = 0
    if nbh > 22528:
        nbh = 22528
    return nbh


# /*
# +--------------------------------------------------------------------------+
# | * Test Vectors (added for CHStone)                                       |
# |     test_data : input data                                               |
# |     test_compressed : expected output data for "encode"                  |
# |     test_result : expected output data for "decode"                      |
# +--------------------------------------------------------------------------+
# */

SIZE=100
IN_END=100

test_data = [
    0x44, 0x44, 0x44, 0x44, 0x44,
    0x44, 0x44, 0x44, 0x44, 0x44,
    0x44, 0x44, 0x44, 0x44, 0x44,
    0x44, 0x44, 0x43, 0x43, 0x43,
    0x43, 0x43, 0x43, 0x43, 0x42,
    0x42, 0x42, 0x42, 0x42, 0x42,
    0x41, 0x41, 0x41, 0x41, 0x41,
    0x40, 0x40, 0x40, 0x40, 0x40,
    0x40, 0x40, 0x40, 0x3f, 0x3f,
    0x3f, 0x3f, 0x3f, 0x3e, 0x3e,
    0x3e, 0x3e, 0x3e, 0x3e, 0x3d,
    0x3d, 0x3d, 0x3d, 0x3d, 0x3d,
    0x3c, 0x3c, 0x3c, 0x3c, 0x3c,
    0x3c, 0x3c, 0x3c, 0x3c, 0x3b,
    0x3b, 0x3b, 0x3b, 0x3b, 0x3b,
    0x3b, 0x3b, 0x3b, 0x3b, 0x3b,
    0x3b, 0x3b, 0x3b, 0x3b, 0x3b,
    0x3b, 0x3b, 0x3b, 0x3b, 0x3b,
    0x3b, 0x3b, 0x3c, 0x3c, 0x3c,
    0x3c, 0x3c, 0x3c, 0x3c, 0x3c
]

compressed = [0] * SIZE
result = [0] * SIZE

test_compressed = [
    0xfd, 0xde, 0x77, 0xba, 0xf2, 
    0x90, 0x20, 0xa0, 0xec, 0xed, 
    0xef, 0xf1, 0xf3, 0xf4, 0xf5, 
    0xf5, 0xf5, 0xf5, 0xf6, 0xf6, 
    0xf6, 0xf7, 0xf8, 0xf7, 0xf8, 
    0xf7, 0xf9, 0xf8, 0xf7, 0xf9, 
    0xf8, 0xf8, 0xf6, 0xf8, 0xf8, 
    0xf7, 0xf9, 0xf9, 0xf9, 0xf8, 
    0xf7, 0xfa, 0xf8, 0xf8, 0xf7, 
    0xfb, 0xfa, 0xf9, 0xf8, 0xf8
]
test_result = [
    0, -1, -1, 0, 0, 
    -1, 0, 0, -1, -1, 
    0, 0, 0x1, 0x1, 0, 
    -2, -1, -2, 0, -4, 
    0x1, 0x1, 0x1, -5, 0x2, 
    0x2, 0x3, 0xb, 0x14, 0x14, 
    0x16, 0x18, 0x20, 0x21, 0x26, 
    0x27, 0x2e, 0x2f, 0x33, 0x32, 
    0x35, 0x33, 0x36, 0x34, 0x37, 
    0x34, 0x37, 0x35, 0x38, 0x36, 
    0x39, 0x38, 0x3b, 0x3a, 0x3f, 
    0x3f, 0x40, 0x3a, 0x3d, 0x3e, 
    0x41, 0x3c, 0x3e, 0x3f, 0x42, 
    0x3e, 0x3b, 0x37, 0x3b, 0x3e, 
    0x41, 0x3b, 0x3b, 0x3a, 0x3b, 
    0x36, 0x39, 0x3b, 0x3f, 0x3c, 
    0x3b, 0x37, 0x3b, 0x3d, 0x41, 
    0x3d, 0x3e, 0x3c, 0x3e, 0x3b, 
    0x3a, 0x37, 0x3b, 0x3e, 0x41, 
    0x3c, 0x3b, 0x39, 0x3a, 0x36
]

def adpcm_main():
    # reset, initialize required memory
    reset()

    for i in range(0, IN_END, 2):
        compressed[int(i/2)] = encode(test_data[i], test_data[i + 1])
    for i in range(0, IN_END, 2):
        decode(compressed[int(i/2)])
        result[i] = xout1
        result[i + 1] = xout2
def main():
    main_result = 0
    adpcm_main()
    for i in range(int(IN_END / 2)):
        if compressed[i] != test_compressed[i]:
            main_result += 1
    for i in range(IN_END):
        if result[i] != test_result[i]:
            main_result += 1
    dump()
    print(main_result)
    return main_result

main()
