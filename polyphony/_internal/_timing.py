__all__ = [
    'clksleep',
    'fence',
    'wait_edge',
    'wait_rising',
    'wait_falling',
    'wait_value',
]


def clksleep(clk_cycles) -> None:
    pass

@inlinelib
def fence():
    clksleep(0)

    
def wait_edge(old, new, *ports):
    pass

def wait_rising(*ports):
    pass

def wait_falling(*ports):
    pass

def wait_value(value, *ports):
    pass
