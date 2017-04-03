__all__ = [
    'clksleep',
    'clkfence',
    'wait_edge',
    'wait_rising',
    'wait_falling',
    'wait_value',
]

@builtin
def clksleep(clk_cycles:int) -> None:
    pass


@inlinelib
def clkfence() -> None:
    clksleep(0)


@builtin
def wait_edge(old:int, new:int, *ports:polyphony.io.Port) -> None:
    pass


@builtin
def wait_rising(*ports:polyphony.io.Port) -> None:
    pass


@builtin
def wait_falling(*ports:polyphony.io.Port) -> None:
    pass


@builtin
def wait_value(value:int, *ports:polyphony.io.Port) -> None:
    pass
