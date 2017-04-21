'''
The polyphony.timing library provides functions for timing control.
'''
import time
from . import io
from . import typing

__all__ = [
    'clksleep',
    'clkfence',
    'wait_edge',
    'wait_rising',
    'wait_falling',
    'wait_value',
]


def clksleep(clk_cycles):
    '''
    During the specified clk_cycles, stop processing.
    This function is used for the timing control in the hardware level.

    *Parameters:*
        clk_cycles : int
            The number of cycles of clock signal.


    *Notes:*
        This function does not work as expectedly in the Python interpreter.
    '''
    assert clk_cycles >= 0
    time.sleep(0.001 * clk_cycles)


def clkfence():
    '''
    This function guarantees that the instructions before and after this function are executed in different steps.
    This function is used for the timing control in the hardware level.

    *Notes:*
        This function does not work as expectedly in the Python interpreter.
    '''
    clksleep(0)


def wait_edge(old, new, *ports):
    '''
    Wait until the signal of the specified port changes from 'old' to 'new'.

    *Parameters:*
        old : A data type of the port

        new : A data type of the port

        ports : Port
    '''

    if not ports:
        raise TypeError("wait_edge() missing required argument: 'ports'")
    cv = io._create_cond()
    for p in ports:
        if p._dtype is not typing.bit and p._dtype is not bool:
            raise TypeError("'wait_rising' and 'wait_falling' functions take io.Port(bit) or io.Port(bool) instances")
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
    '''
    Wait until the signal of the specified port with bit dtype changes from 0 to 1.

    *Parameters:*
        ports : Port with bit dtype
    '''
    if not ports:
        raise TypeError("wait_rising() missing required argument: 'ports'")
    for p in ports:
        if p._dtype is not typing.bit and p._dtype is not bool:
            raise TypeError("'wait_rising' function takes io.Port(bit) or io.Port(bool) instances")
    wait_edge(0, 1, *ports)


def wait_falling(*ports):
    '''
    Wait until the signal of the specified port with bit dtype changes from 1 to 0.

    *Parameters:*
        ports : Port with bit dtype
    '''
    if not ports:
        raise TypeError("wait_falling() missing required argument: 'ports'")
    for p in ports:
        if p._dtype is not typing.bit and p._dtype is not bool:
            raise TypeError("'wait_falling' function takes io.Port(bit) or io.Port(bool) instances")
    wait_edge(1, 0, *ports)


def wait_value(value, *ports):
    '''
    Wait until the signal of the specified port changes specified value.

    *Parameters:*
        value : A data type of the port

        ports : Port
    '''
    if not ports:
        raise TypeError("wait_value() missing required argument: 'ports'")
    cv = io._create_cond()
    for p in ports:
        p._add_cv(cv)
    with cv:
        while not all([p.rd() == value for p in ports]) and io._io_enabled:
            cv.wait()
    for p in ports:
        p._del_cv(cv)
    io._remove_cond(cv)
