from .ir import *
from .env import env

UNIT_STEP = 1
CALL_MINIMUM_STEP = 3


def get_call_latency(call, stm):
    # FIXME: It is better to ask HDLInterface the I/O latency
    is_pipelined = stm.block.synth_params['scheduling'] == 'pipeline'
    if call.func_scope().is_method() and call.func_scope().parent.is_port():
        receiver = call.func.tail()
        assert receiver.typ.is_port()
        if call.func_scope().base_name == 'rd':
            dummy_read = stm.is_a(EXPR)
            if dummy_read:
                return 0
            else:
                return UNIT_STEP * 1
        return UNIT_STEP
    elif call.func_scope().parent.name.startswith('polyphony.Net'):
        if call.func_scope().base_name == 'rd':
            if stm.is_a(MOVE):
                if stm.dst.symbol().is_alias():
                    return 0
                else:
                    return UNIT_STEP * 1
            else:
                return 0
    elif call.func_scope().asap_latency > 0:
        return UNIT_STEP * call.func_scope().asap_latency
    return UNIT_STEP * CALL_MINIMUM_STEP


def get_syscall_latency(call):
    if call.sym.name == 'polyphony.timing.clksleep':
        _, cycle = call.args[0]
        assert cycle.is_a(CONST)
        return cycle.value
    elif call.sym.name.startswith('polyphony.timing.wait_'):
        return 0
    if call.sym.name in ('assert', 'print'):
        return 0
    return UNIT_STEP


def _get_latency(tag):
    assert isinstance(tag, IR)
    if tag.is_a(MOVE):
        if tag.dst.is_a(TEMP) and tag.dst.sym.is_alias():
            return 0
        elif tag.src.is_a(CALL):
            return get_call_latency(tag.src, tag)
        elif tag.src.is_a(NEW):
            return 0
        elif tag.src.is_a(TEMP) and tag.src.sym.typ.is_port():
            return 0
        elif tag.dst.is_a(ATTR):
            if tag.dst.symbol().is_alias():
                return 0
            return UNIT_STEP * 1
        elif tag.src.is_a(MREF):
            memnode = tag.src.mem.symbol().typ.get_memnode()
            #if memnode.is_immutable() or not memnode.is_writable() or memnode.can_be_reg():
            return UNIT_STEP
            return UNIT_STEP * env.config.internal_ram_load_latency, UNIT_STEP * 1
        elif tag.dst.is_a(TEMP) and tag.dst.symbol().typ.is_seq():
            memnode = tag.dst.symbol().typ.get_memnode()
            if tag.src.is_a(ARRAY):
                if True: # memnode.can_be_reg():
                    return 1
                elif not memnode.is_writable():
                    return 0
                else:
                    return UNIT_STEP * len(tag.src.items * tag.src.repeat.value)
            if tag.src.is_a(TEMP) and tag.src.symbol().typ.is_seq():
                if False:  # not memnode.can_be_reg():
                    return 0, 0
        if tag.dst.symbol().is_alias():
            return 0
    elif tag.is_a(EXPR):
        if tag.exp.is_a(CALL):
            return get_call_latency(tag.exp, tag)
        elif tag.exp.is_a(SYSCALL):
            return get_syscall_latency(tag.exp)
        elif tag.exp.is_a(MSTORE):
            memnode = tag.exp.mem.symbol().typ.get_memnode()
            if True:  # memnode.can_be_reg():
                return UNIT_STEP * 1
            return UNIT_STEP * env.config.internal_ram_store_latency, UNIT_STEP * 1
    elif tag.is_a(PHI):
        #if tag.var.symbol().typ.is_seq() and not tag.var.symbol().typ.get_memnode().can_be_reg():
        #    return 0
        if tag.var.symbol().is_alias():
            return 0
    elif tag.is_a(UPHI):
        if tag.var.symbol().is_alias():
            return 0
    return UNIT_STEP


def get_latency(tag):
    l = _get_latency(tag)
    if isinstance(l, tuple):
        return l[0], l[1]
    else:
        return l, l
