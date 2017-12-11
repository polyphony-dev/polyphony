from polyphony import module
from polyphony import is_worker_running
from polyphony.io import Queue
from polyphony.typing import int4, int12, List, Tuple
from polyphony import pipelined


def max(a:int12, b:int12) -> int12:
    return a if a > b else b


def min(a:int12, b:int12) -> int12:
    return a if a < b else b


def normalize(v:int12):
    return min(max(128 + v, 0), 255)


K:Tuple[int4] = (-1, 0, 1,
                 -2, 0, 2,
                 -1, 0, 1)


def filter3x3(r0, r1, r2, r3, r4, r5, r6, r7, r8):
    a0 = r0 * K[0]
    a1 = r1 * K[1]
    a2 = r2 * K[2]
    a3 = r3 * K[3]
    a4 = r4 * K[4]
    a5 = r5 * K[5]
    a6 = r6 * K[6]
    a7 = r7 * K[7]
    a8 = r8 * K[8]
    s = a0 + a1 + a2 + a3 + a4 + a5 + a6 + a7 + a8
    return normalize(s)


@module
class PipelinedStreamFilter:
    def __init__(self, width, height, blank_size):
        self.inq = Queue(int12, 'in', maxsize=8)
        self.outq = Queue(int12, 'out', maxsize=8)
        self.append_worker(self.worker, width, height, blank_size)

    def worker(self, width, height, blank_size):
        buf0:List[int12] = [255] * (width + blank_size)
        buf1:List[int12] = [255] * (width + blank_size)
        buf2:List[int12] = [255] * (width + blank_size)
        line0 = buf0
        line1 = buf1
        line2 = buf2
        phase = 0
        y = blank_size
        r0:int12 = 255
        r1:int12 = 255
        r2:int12 = 255
        r3:int12 = 255
        r4:int12 = 255
        r5:int12 = 255
        r6:int12 = 255
        r7:int12 = 255
        r8:int12 = 255
        while is_worker_running():
            for x in pipelined(range(blank_size, width + blank_size)):
                d2 = self.inq.rd()
                line2[x] = d2
                d1 = line1[x]
                d0 = line0[x]
                r0, r1, r2 = r1, r2, d0
                r3, r4, r5 = r4, r5, d1
                r6, r7, r8 = r7, r8, d2
                out = filter3x3(r0, r1, r2,
                                r3, r4, r5,
                                r6, r7, r8)
                print('out', out)
                self.outq.wr(out)
            phase = (phase + 1) % 3
            if phase == 0:
                line0 = buf0
                line1 = buf1
                line2 = buf2
            elif phase == 1:
                line0 = buf1
                line1 = buf2
                line2 = buf0
            else:
                line0 = buf2
                line1 = buf0
                line2 = buf1
            r0 = r1 = r2 = 255
            r3 = r4 = r5 = 255
            r6 = r7 = r8 = 255
            y += 1
            if y == height + blank_size:
                # TODO:
                break


if __name__ == '__main__':
    filter = PipelinedStreamFilter(512, 512, 2)
