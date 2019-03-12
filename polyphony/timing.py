'''
The polyphony.timing library provides functions for timing control.
'''
import threading
from . import base
from . import io
from . import typing


# @timed decorator
def timed(func):
    # TODO: error check
    def _timed_decorator(*args, **kwargs):
        return func(*args, **kwargs)
    return _timed_decorator


def _wait_cycle():
    if not io._io_enabled:
        raise io.PolyphonyIOException()
    worker = base._worker_map[threading.get_ident()]
    with base._cycle_update_cv:
        worker.cycle += 1
        base._cycle_update_cv.notify()

    base._serializer.wait(threading.get_ident())

    #print('restart', worker.func.__name__)
    if not io._io_enabled:
        raise io.PolyphonyIOException()


def clksleep(clk_cycles):
    for i in range(clk_cycles + 1):
        _wait_cycle()


def clkfence():
    _wait_cycle()


def clkrange(cycles):
    for i in range(cycles):
        _wait_cycle()
        yield i


def clktime():
    return base._simulation_time


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
    for p in ports:
        if p._dtype is not typing.bit and p._dtype is not bool:
            raise TypeError("wait_edge() takes io.Port(bit) or io.Port(bool) instances")
    while not all([p.edge(old, new) for p in ports]):
        clkfence()


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
            raise TypeError("wait_rising() takes io.Port(bit) or io.Port(bool) instances")
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
            raise TypeError("wait_falling() takes io.Port(bit) or io.Port(bool) instances")
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
    while not all([p.rd() == value for p in ports]):
        clkfence()
