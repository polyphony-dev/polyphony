from polyphony.typing import uint64

@decorator
def timed() -> None:
    pass


@builtin
def clksleep(clk_cycles:int) -> None:
    pass


@inlinelib
def clkfence() -> None:
    clksleep(1)


@builtin
def clkrange(clk_cycles:int=None) -> None:
    pass


@builtin
def clktime() -> uint64:
    pass


@builtin
def wait_until(pred:function) -> bool:
    pass


@inlinelib
def wait_edge(old, new, port) -> None:
    wait_until(lambda: port.edge(old, new))


@inlinelib
def wait_rising(port) -> None:
    wait_until(lambda: port.edge(0, 1))


@inlinelib
def wait_falling(port) -> None:
    wait_until(lambda: port.edge(1, 0))


@inlinelib
def wait_value(value, port) -> None:
    wait_until(lambda: port.rd() == value)
