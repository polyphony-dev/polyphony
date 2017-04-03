from .ir import *
from .dataflow import DataFlowGraph

UNIT_STEP = 1
CALL_MINIMUM_STEP = 5


def get_call_latency(call):
    if call.func_scope.name.startswith('polyphony.io.Queue') and call.func_scope.name.endswith('.rd'):
        return UNIT_STEP * 3
    elif call.func_scope.name.startswith('polyphony.io.Queue') and call.func_scope.name.endswith('.wr'):
        return UNIT_STEP * 3
    elif call.func_scope.is_method() and call.func_scope.parent.is_port():
        receiver = call.func.tail()
        assert receiver.typ.is_port()
        protocol = receiver.typ.get_protocol()
        if call.func_scope.orig_name == 'rd':
            if protocol == 'ready_valid':
                return UNIT_STEP * 2
            elif protocol == 'valid':
                return UNIT_STEP * 2
        elif call.func_scope.orig_name == 'wr':
            if protocol == 'ready_valid':
                return UNIT_STEP * 2
            elif protocol == 'valid':
                return UNIT_STEP * 2
        return UNIT_STEP
    elif call.func_scope.asap_latency > 0:
        return UNIT_STEP * call.func_scope.asap_latency
    return UNIT_STEP * CALL_MINIMUM_STEP


def get_syscall_latency(call):
    if call.sym.name == 'polyphony.timing.clksleep':
        _, cycle = call.args[0]
        assert cycle.is_a(CONST)
        return cycle.value
    elif call.sym.name.startswith('polyphony.timing.wait_'):
        return UNIT_STEP
    return UNIT_STEP


def get_latency(tag):
    if isinstance(tag, DataFlowGraph):
        #TODO:
        return UNIT_STEP * 5

    assert isinstance(tag, IR)
    if tag.is_a(MOVE):
        if tag.src.is_a(CALL):
            return get_call_latency(tag.src)
        elif tag.src.is_a(NEW):
            return 0
        elif tag.src.is_a(TEMP) and tag.src.sym.typ.is_port():
            return 0
        elif tag.dst.is_a(TEMP) and tag.dst.sym.is_alias():
            return 0
        elif tag.dst.is_a(ATTR):
            return UNIT_STEP * 2
        elif tag.src.is_a(ARRAY):
            return UNIT_STEP * len(tag.src.items * tag.src.repeat.value)
        elif tag.src.is_a(MREF):
            memnode = tag.src.mem.symbol().typ.get_memnode()
            if memnode.is_immutable() or not memnode.is_writable():
                return UNIT_STEP
            return UNIT_STEP * 3
        elif tag.src.is_a(MSTORE):
            return UNIT_STEP * 1
    elif tag.is_a(EXPR):
        if tag.exp.is_a(CALL):
            return get_call_latency(tag.exp)
        elif tag.exp.is_a(SYSCALL):
            return get_syscall_latency(tag.exp)
    return UNIT_STEP
