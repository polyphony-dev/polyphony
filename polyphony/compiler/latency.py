from .ir import *
from .dataflow import DataFlowGraph

UNIT_STEP = 1
CALL_MINIMUM_STEP = 4


def get_latency(tag):
    if isinstance(tag, DataFlowGraph):
        #TODO:
        return UNIT_STEP * 5

    assert isinstance(tag, IR)
    if tag.is_a(MOVE):
        if tag.src.is_a(CALL):
            if tag.src.func_scope.name == 'polyphony.io.Queue.rd':
                return UNIT_STEP * 3
            elif tag.src.func_scope.asap_latency > 0:
                return UNIT_STEP * tag.src.func_scope.asap_latency
            return UNIT_STEP * CALL_MINIMUM_STEP
        elif tag.src.is_a(NEW):
            return 0
        elif tag.src.is_a(TEMP) and tag.src.sym.typ.is_port():
            return 0
        elif tag.dst.is_a(TEMP) and tag.dst.sym.is_alias():
            return 0
        elif tag.dst.is_a(ATTR):
            return UNIT_STEP * 2
        elif tag.src.is_a(ARRAY):
            return UNIT_STEP * len(tag.src.items)
        elif tag.src.is_a(MREF):
            memnode = tag.src.mem.symbol().typ.get_memnode()
            if memnode.is_immutable() or not memnode.is_writable():
                return UNIT_STEP
            return UNIT_STEP * 3
        elif tag.src.is_a(MSTORE):
            return UNIT_STEP * 1
    elif tag.is_a(EXPR):
        if tag.exp.is_a(CALL):
            if tag.exp.func_scope.name == 'polyphony.io.Queue.wr':
                return UNIT_STEP * 3
            return UNIT_STEP * CALL_MINIMUM_STEP
        elif tag.exp.is_a(SYSCALL):
            if tag.exp.name == 'polyphony.timing.clksleep':
                _, cycle = tag.exp.args[0]
                assert cycle.is_a(CONST)
                return cycle.value
            elif tag.exp.name.startswith('polyphony.timing.wait_'):
                return UNIT_STEP
    return UNIT_STEP
