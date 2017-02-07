import time, signal
from . import io

__all__ = [
    'clksleep',
    'clkfence',
    'wait_edge',
    'wait_rising',
    'wait_falling',
    'wait_value',
]

def clksleep(clk_cycles):
    assert clk_cycles >= 0
    time.sleep(0.001 * clk_cycles)

def clkfence():
    clksleep(0)
    
def wait_edge(old, new, *ports):
    cv = io._create_cond()
    for p in ports:
        if not isinstance(p, io.Bit):
            raise TypeError("'wait_rising' and 'wait_falling' functions take io.Bit instances")
        p._add_cv(cv)
    with cv:
        while io._io_enabled:
            cv.wait()
            if all([p._rd_old() == old and p.rd() == new for p in ports]):
                break
    for p in ports:
        p._del_cv(cv)
    io._remove_cond(cv)


def wait_rising(*ports):
    for p in ports:
        if not isinstance(p, io.Bit):
            raise TypeError("'wait_rising' function takes io.Bit instances")
    wait_edge(0, 1, *ports)


def wait_falling(*ports):
    for p in ports:
        if not isinstance(p, io.Bit):
            raise TypeError("'wait_falling' function takes io.Bit instances")
    wait_edge(1, 0, *ports)


def wait_value(value, *ports):
    cv = io._create_cond()
    for p in ports:
        p._add_cv(cv)
    with cv:
        while not all([p.rd() == value for p in ports]) and io._io_enabled:
            cv.wait()
    for p in ports:
        p._del_cv(cv)
    io._remove_cond(cv)
