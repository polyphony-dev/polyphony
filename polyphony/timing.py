'''
The polyphony.timing library provides functions for timing control.
'''
from . import typing
from .simulator import clkfence, clksleep, clktime, clkrange

# @timed decorator
def timed(cls):
    return cls


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
