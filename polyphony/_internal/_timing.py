__all__ = [
    'clksleep',
    'clkfence',
    'wait_edge',
    'wait_rising',
    'wait_falling',
    'wait_value',
]


def clksleep(clk_cycles:int) -> None:
    pass


@inlinelib
def clkfence():
    clksleep(0)


def wait_edge(old:int, new:int, *ports:polyphony.io._DataPort) -> None:
    pass


def wait_rising(*ports:polyphony.io.Bit) -> None:
    pass


def wait_falling(*ports:polyphony.io.Bit) -> None:
    pass


def wait_value(value:int, *ports:polyphony.io._DataPort) -> None:
    pass
