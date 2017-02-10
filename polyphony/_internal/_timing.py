__all__ = [
    'clksleep',
    'clkfence',
    'wait_edge',
    'wait_rising',
    'wait_falling',
    'wait_value',
]


def clksleep(clk_cycles) -> None:
    pass


@inlinelib
def clkfence():
    clksleep(0)


def wait_edge(old, new, *ports) -> None:
    pass


def wait_rising(*ports) -> None:
    pass


def wait_falling(*ports) -> None:
    pass


def wait_value(value, *ports) -> None:
    pass
