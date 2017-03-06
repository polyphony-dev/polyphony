import polyphony
from polyphony.io import Bit, Uint
from polyphony.timing import clksleep, clkfence, wait_rising, wait_falling


CONVST_PULSE_CYCLE = 10
CONVERSION_CYCLE = 40


@polyphony.module
class AD7091R_SPIC:
    def __init__(self):
        self.sclk = Bit()
        self.sdo  = Bit()
        self.sdi  = Bit()
        self.convst_n = Bit(init=1)
        self.cs_n = Bit(init=1)

        self.dout = Uint(width=12)
        self.chout = Uint(width=3)
        self.din = Uint(width=16)
        self.data_ready = Bit()
        self.append_worker(self.main)

    def main(self):
        while polyphony.is_worker_running():
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
            clksleep(1)

            for i in range(16):
                self.sclk.wr(0)
                sdi_tmp = 1 if (self.din() & (1 << (15 - i))) else 0
                self.sdi.wr(sdi_tmp)
                clksleep(1)

                self.sclk.wr(1)
                sdo_tmp = sdo_tmp << 1 | self.sdo.rd()

            self.sclk.wr(0)
            self.dout.wr(sdo_tmp & 0x0fff)
            self.chout.wr((sdo_tmp & 0x7000) >> 12)
            self.cs_n.wr(1)
            clkfence()
            self.data_ready.wr(1)


@polyphony.testbench
def test(spic):
    datas = (0xdead, 0xbeef, 0xffff, 0x0000, 0x800)
    for data in datas:
        print(data)
        wait_falling(spic.convst_n)
        print('convst_n fall', spic.convst_n())
        wait_rising(spic.convst_n)
        print('convst_n rise', spic.convst_n())
        wait_falling(spic.cs_n)
        print('cs_n fall', spic.cs_n())
        spic.din.wr(0b1111000011110000)
        for i in range(16):
            databit = 1 if data & (1 << (15 - i)) else 0
            spic.sdo.wr(databit)
            wait_rising(spic.sclk)

        wait_rising(spic.cs_n)
        wait_rising(spic.data_ready)
        clksleep(1)
        assert spic.dout() == data & 0x0fff
        assert spic.chout() == (data & 0x7000) >> 12


spic = AD7091R_SPIC()
test(spic)
