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
        if hasattr(func, 'cls'):
            cls = getattr(func, 'cls')
            cls.timed_module = True
        elif hasattr(func, 'func'):  # is decorator
            func.func.timed_func = True
        else:
            func.timed_func = True
        return func(*args, **kwargs)
    _timed_decorator.func = func
    _timed_decorator.__dict__.update(func.__dict__)
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
    for i in range(clk_cycles):
        _wait_cycle()


def clkfence():
    _wait_cycle()


def clkrange(cycles=None):
    if cycles:
        for i in range(cycles):
            _wait_cycle()
            yield i
        _wait_cycle()
    else:
        i = 0
        while True:
            _wait_cycle()
            yield i
            i += 1


def clktime():
    return base._simulation_time


def wait_until(pred):
    '''
    Wait until the predicate function returns True.

    *Parameters:*
        pred : A predicate function
    '''
    while not pred():
        clkfence()


def wait_edge(old, new, port):
    '''
    Wait until the signal of the specified port changes from 'old' to 'new'.

    *Parameters:*
        old : A data type of the port

        new : A data type of the port

        port : Port
    '''
    if not port:
        raise TypeError("wait_edge() missing required argument: 'port'")
    if port._dtype is not typing.bit and port._dtype is not bool:
        raise TypeError("wait_edge() takes io.Port(bit) or io.Port(bool) instance")
    wait_until(lambda:port.edge(old, new))


def wait_rising(port):
    '''
    Wait until the signal of the specified port with bit dtype changes from 0 to 1.

    *Parameters:*
        port : Port with bit dtype
    '''
    if not port:
        raise TypeError("wait_rising() missing required argument: 'port'")
    if port._dtype is not typing.bit and port._dtype is not bool:
        raise TypeError("wait_rising() takes io.Port(bit) or io.Port(bool) instance")
    wait_edge(0, 1, port)


def wait_falling(port):
    '''
    Wait until the signal of the specified port with bit dtype changes from 1 to 0.

    *Parameters:*
        port : Port with bit dtype
    '''
    if not port:
        raise TypeError("wait_falling() missing required argument: 'port'")
    if port._dtype is not typing.bit and port._dtype is not bool:
        raise TypeError("wait_falling() takes io.Port(bit) or io.Port(bool) instance")
    wait_edge(1, 0, port)


def wait_value(value, port):
    '''
    Wait until the signal of the specified port changes specified value.

    *Parameters:*
        value : A data type of the port

        port : Port
    '''
    if not port:
        raise TypeError("wait_value() missing required argument: 'port'")
    wait_until(lambda:port.rd() == value)
