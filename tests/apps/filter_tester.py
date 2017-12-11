from polyphony import testbench
from polyphony import module
from polyphony.io import Port
from polyphony.typing import int12, List, Tuple
from polyphony import rule, pipelined
from sobel_filter import PipelinedStreamFilter as StreamFilter


# NOTE: env.internal_ram_threshold_size = 0 is required for this test.


TEST_DATA:List[int12] = [
    141, 140, 137, 128, 126, 121, 119, 116, 113,
    110, 114, 117, 114, 117, 124, 128, 132, 137,
    141, 143, 143, 148, 152, 146, 148, 145, 143,
    142, 147, 145, 147, 147, 144, 145, 149, 150,
]

EXPECTED_DATA:List[int12] = [
    14, 13, 124, 116, 117, 121, 121, 123, 122,
    0, 0, 127, 104, 106, 124, 125, 126, 125,
    0, 0, 140, 121, 126, 139, 139, 138, 135,
    0, 0, 142, 138, 148, 131, 129, 139, 132
]


W = 9
H = 4


@module
class FilterTester:
    def __init__(self):
        self.start = Port(bool, 'in', protocol='ready_valid')
        self.finish = Port(bool, 'out', protocol='ready_valid')
        self.sobel = StreamFilter(W, H, 2)
        self.append_worker(self.test_source)
        self.append_worker(self.test_sink)

    def test_source(self):
        self.start()
        for y in range(H):
            for x in pipelined(range(W)):
                idx = y * W + x
                p = TEST_DATA[idx]
                print('in', p)
                self.sobel.inq.wr(p)

    def test_sink(self):
        output:List[int12] = [None] * (W * H)
        for y in range(H):
            for x in pipelined(range(W)):
                idx = y * W + x
                out = self.sobel.outq.rd()
                print('out', out)
                output[idx] = out
        for i in range(len(output)):
            if output[i] != EXPECTED_DATA[i]:
                print('error', i, output[i], EXPECTED_DATA[i])
        self.finish(True)


@testbench
def test_stream(tester):
    tester.start.wr(True)
    tester.finish.rd()


if __name__ == '__main__':
    tester = FilterTester()
    test_stream(tester)
