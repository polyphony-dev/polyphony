import polyphony
from polyphony.io import Port
from polyphony.typing import bit, uint3, uint12, uint16
from polyphony.timing import timed, clksleep, clkfence, clkrange, clktime, wait_rising, wait_falling


CONVST_PULSE_CYCLE = 10
CONVERSION_CYCLE = 40

@timed
@polyphony.module
class AD7091R_SPIC:
    def __init__(self):
        self.sclk = Port(bit, 'out')
        self.sdo  = Port(bit, 'in')
        self.sdi  = Port(bit, 'out')
        self.convst_n = Port(bit, 'out', init=1)
        self.cs_n = Port(bit, 'out', init=1)

        self.dout = Port(uint12, 'out')
        self.chout = Port(uint3, 'out')
        self.din = Port(uint16, 'in')
        self.data_ready = Port(bit, 'out')
        self.append_worker(self.main, loop=True)

    def main(self):
        #clkfence()
        #while polyphony.is_worker_running():
        self.convst_n.wr(1)
        self.cs_n.wr(1)
        self.data_ready.wr(0)
        clkfence()

        self.convst_n.wr(0)
        clksleep(CONVST_PULSE_CYCLE)

        self.convst_n.wr(1)
        clksleep(CONVERSION_CYCLE)

        # starting ADC I/O
        self.cs_n.wr(0)
        sdo_tmp = 0
        clkfence()

        for i in clkrange(16):
            self.sclk.wr(0)
            sdi_tmp = 1 if (self.din.rd() & (1 << (15 - i))) else 0
            self.sdi.wr(sdi_tmp)
            clksleep(2)

            self.sclk.wr(1)
            clkfence()
            sdo_d = self.sdo.rd()
            sdo_tmp = sdo_tmp << 1 | sdo_d
            #print('sdo read!', i, sdo_d)

        self.sclk.wr(0)
        self.dout.wr(sdo_tmp & 0x0fff)
        self.chout.wr((sdo_tmp & 0x7000) >> 12)
        self.cs_n.wr(1)
        clkfence()
        self.data_ready.wr(1)


@timed
@polyphony.testbench
def test(spic):
    expected_times = (1, 120, 239, 358, 477)
    data = (0xdead, 0xbeef, 0xffff, 0x0000, 0x800)
    for i in clkrange(len(data)):
        assert expected_times[i] == clktime()
        d = data[i]
        print('send: data ', d & 0x0fff, 'ch', (d & 0x7000)>>12)
        wait_falling(spic.convst_n)
        wait_rising(spic.convst_n)
        wait_falling(spic.cs_n)
        spic.din.wr(0b1111000011001010)
        expected_din = (1, 1, 1, 1, 0, 0, 0, 0, 1, 1, 0, 0, 1, 0, 1, 0)
        for j in clkrange(16):
            databit = 1 if d & (1 << (15 - j)) else 0
            #print('sdo write from test', i, databit)
            spic.sdo.wr(databit)
            clkfence()
            assert spic.sdi.rd() == expected_din[j]
            wait_rising(spic.sclk)
        wait_rising(spic.cs_n)
        wait_rising(spic.data_ready)
        print('recv: data ', spic.dout.rd(), 'ch', spic.chout.rd())
        assert spic.dout.rd() == (d & 0x0fff)
        assert spic.chout.rd() == ((d & 0x7000) >> 12)


spic = AD7091R_SPIC()
test(spic)
