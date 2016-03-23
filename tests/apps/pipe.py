from polyphony import testbench

def proc1(indata:list, outdata:list):
    for i in range(len(indata)):
        outdata[i] = indata[i] * 2

def proc2(indata:list, outdata:list):
    for i in range(len(indata)):
        outdata[i] = indata[i] + 1

def proc3(indata:list, outdata:list):
    for i in range(len(indata)):
        outdata[i] = indata[i] + 10

# block pipeline with ping-pong buffering
def pipe(stage, indata:list, outdata:list):
    proc1_buf_A = [None] * 16
    proc1_buf_B = [None] * 16
    proc2_buf_A = [None] * 16
    proc2_buf_B = [None] * 16

    if stage & 1:
        proc1_out = proc1_buf_A
        proc2_in  = proc1_buf_B
        proc2_out = proc2_buf_A
        proc3_in  = proc2_buf_B
    else:
        proc1_out = proc1_buf_B
        proc2_in  = proc1_buf_A
        proc2_out = proc2_buf_B        
        proc3_in  = proc2_buf_A
    proc1(indata, proc1_out)
    proc2(proc2_in, proc2_out)
    proc3(proc3_in, outdata)

@testbench
def test():
    out = [None] * 16
    data1 = [1] * 16
    data2 = [2] * 16
    data3 = [3] * 16
    pipe(1, data1, out)
    pipe(2, data2, out)
    pipe(1, data3, out)
    for o in out: print(o)
    pipe(2, data1, out)
    for o in out: print(o)
    pipe(1, data2, out)
    for o in out: print(o)
    pipe(2, data3, out)
    for o in out: print(o)

test()
