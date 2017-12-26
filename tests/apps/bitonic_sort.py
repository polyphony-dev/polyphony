import polyphony
from polyphony import is_worker_running
from polyphony.io import Port
from polyphony.timing import clksleep, clkfence


ASCENDING = True
DESCENDING = False

proto = 'ready_valid'
#proto = 'none'


@polyphony.pure
def bitonic_indices(size, blocks, offset):
    for i in range(0, size):
        if (i % (offset << 1)) >= offset:
            continue
        direction = ASCENDING if (i // blocks) % 2 == 0 else DESCENDING
        ii = i + offset
        yield i, ii, direction


@polyphony.pure
def bitonic_nets(size):
    rank = 0
    stage = 0
    while size > (1 << rank):
        for i in range(0, rank + 1):
            blocks = 1 << (rank + 1)
            offset = 1 << (rank - i)
            indices = []
            for i, ii, direction in bitonic_indices(size, blocks, offset):
                indices.append((i, ii, direction))
            yield stage, indices
            stage += 1
        rank += 1


@polyphony.pure
def num_of_stages(size):
    rank = 0
    stage = 0
    while size > (1 << rank):
        for i in range(0, rank + 1):
            stage += 1
        rank += 1
    return stage


@polyphony.pure
def make_io_ports(m, size, inports, outports):
    for i in range(size):
        inname = 'i' + str(i)
        outname = 'o' + str(i)
        inport = Port(int, 'in', protocol=proto)
        outport = Port(int, 'out', protocol=proto)
        setattr(m, inname, inport)
        setattr(m, outname, outport)
        inports.append(inport)
        outports.append(outport)


@polyphony.module
class BitonicSorter:
    @polyphony.pure
    def __init__(self, size):
        inports = []
        outports = []
        make_io_ports(self, size, inports, outports)

        ports = []
        ports.append(inports)
        stages_ = num_of_stages(size)
        for i in range(stages_ - 1):
            localports = [Port(int, 'any', protocol=proto) for i in range(size)]
            ports.append(localports)
        ports.append(outports)

        for stage, indices in bitonic_nets(size):
            ports_cur = ports[stage]
            ports_next = ports[stage + 1]
            for i, ii, direction in indices:
                i1 = ports_cur[i]
                i2 = ports_cur[ii]
                o1 = ports_next[i]
                o2 = ports_next[ii]
                self.append_worker(self.compare, i1, i2, o1, o2, direction)
                #print(i, ii, direction)
                #print(i1, i2, o1, o2, direction)
        #del i1, i2, o1, o2

    def compare(self, i1, i2, o1, o2, di):
        while is_worker_running():
            d1 = i1.rd()
            d2 = i2.rd()
            if (d1 < d2) == di:
                o1.wr(d1)
                o2.wr(d2)
            else:
                o1.wr(d2)
                o2.wr(d1)


@polyphony.testbench
def test_8_1(sorter):
    sorter.i0.wr(7)
    sorter.i1.wr(8)
    sorter.i2.wr(3)
    sorter.i3.wr(2)
    sorter.i4.wr(1)
    sorter.i5.wr(4)
    sorter.i6.wr(5)
    sorter.i7.wr(6)

    clkfence()

    assert 1 == sorter.o0.rd()
    assert 2 == sorter.o1.rd()
    assert 3 == sorter.o2.rd()
    assert 4 == sorter.o3.rd()
    assert 5 == sorter.o4.rd()
    assert 6 == sorter.o5.rd()
    assert 7 == sorter.o6.rd()
    assert 8 == sorter.o7.rd()


@polyphony.testbench
def test_8_2(sorter):
    sorter.i0.wr(6)
    sorter.i1.wr(4)
    sorter.i2.wr(8)
    sorter.i3.wr(2)
    sorter.i4.wr(3)
    sorter.i5.wr(5)
    sorter.i6.wr(7)
    sorter.i7.wr(1)

    clkfence()

    assert 1 == sorter.o0.rd()
    assert 2 == sorter.o1.rd()
    assert 3 == sorter.o2.rd()
    assert 4 == sorter.o3.rd()
    assert 5 == sorter.o4.rd()
    assert 6 == sorter.o5.rd()
    assert 7 == sorter.o6.rd()
    assert 8 == sorter.o7.rd()


sorter1 = BitonicSorter(8)
test_8_1(sorter1)

sorter2 = BitonicSorter(8)
test_8_2(sorter2)


