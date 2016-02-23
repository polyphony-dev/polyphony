from .ir import ARRAY, MREF, MSTORE, CALL, MOVE, EXPR
from .dataflow import DataFlowGraph

MINIMUM_STEP = 1
CALL_MINIMUM_STEP = MINIMUM_STEP * 5

def get_latency(tag):
    if isinstance(tag, MOVE):
        if isinstance(tag.src, CALL):
            return CALL_MINIMUM_STEP
        elif tag.dst.sym.is_condition():
            return 0
        elif isinstance(tag.src, ARRAY):
            return MINIMUM_STEP * len(tag.src.items)
        elif isinstance(tag.src, MREF):
            return MINIMUM_STEP * 3
        elif isinstance(tag.src, MSTORE):
            return MINIMUM_STEP * 1
    elif isinstance(tag, EXPR):
        if isinstance(tag.exp, CALL):
            return CALL_MINIMUM_STEP
    elif isinstance(tag, DataFlowGraph):
        #TODO:
        return MINIMUM_STEP * 5
    return MINIMUM_STEP
