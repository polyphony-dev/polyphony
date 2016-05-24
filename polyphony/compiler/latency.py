from .ir import *
from .dataflow import DataFlowGraph

MINIMUM_STEP = 1
CALL_MINIMUM_STEP = MINIMUM_STEP * 5

def get_latency(tag):
    if isinstance(tag, DataFlowGraph):
        #TODO:
        return MINIMUM_STEP * 5

    assert isinstance(tag, IR)
    if tag.is_a(MOVE):
        if tag.src.is_a(CALL):
            return CALL_MINIMUM_STEP
        elif tag.src.is_a(CTOR):
            return CALL_MINIMUM_STEP
        elif tag.dst.is_a(TEMP) and tag.dst.sym.is_condition():
            return 0
        elif tag.dst.is_a(ATTR):
            return MINIMUM_STEP * 2
        elif tag.src.is_a(ARRAY):
            return MINIMUM_STEP * len(tag.src.items)
        elif tag.src.is_a(MREF):
            return MINIMUM_STEP * 3
        elif tag.src.is_a(MSTORE):
            return MINIMUM_STEP * 1
    elif tag.is_a(EXPR):
        if tag.exp.is_a( CALL):
            return CALL_MINIMUM_STEP
    return MINIMUM_STEP
