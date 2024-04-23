import dataclasses
from .ahdl import *


class AHDLTransformer(object):
    def __init__(self):
        self.current_fsm = None
        self.current_stg = None
        self.current_state = None

    def process(self, hdlmodule):
        self.hdlmodule = hdlmodule
        # FIXME: hdlmodule.decls should not be rewritten directly
        new_decls = []
        for decl in hdlmodule.decls:
            new_decl = self.visit(decl)
            if isinstance(new_decl, AHDL_DECL):
                new_decls.append(new_decl)
            else:
                pass
        hdlmodule.decls = new_decls
        new_funcs = []
        for func in hdlmodule.functions:
            new_func = self.visit(func)
            new_funcs.append(new_func)
        hdlmodule.functions = new_funcs
        for item in hdlmodule.edge_detectors.copy():
            hdlmodule.edge_detectors.remove(item)
            var, old, new = item
            var_ = self.visit(var)
            old_ = self.visit(old)
            new_ = self.visit(new)
            hdlmodule.add_edge_detector(var_, old_, new_)
        for fsm in hdlmodule.fsms.values():
            self.process_fsm(fsm)

    def process_fsm(self, fsm):
        self.current_fsm = fsm
        new_stms = []
        for stm in fsm.reset_stms:
            new_stm = self.visit(stm)
            if isinstance(new_stm, AHDL_MOVE):
                new_stms.append(new_stm)
        fsm.reset_stms = new_stms
        for stg in fsm.stgs:
            self.process_stg(stg)

    def process_stg(self, stg):
        self.current_stg = stg
        new_states = []
        for state in stg.states:
            new_state = self.visit(state)
            if isinstance(new_state, tuple):
                new_states.extend(new_state)
            else:
                assert isinstance(new_state, State)
                new_states.append(new_state)
        stg.set_states(new_states)

    def visit_codes(self, codes:tuple[AHDL_STM, ...]) -> tuple[AHDL_STM, ...]:
        new_codes = []
        for code in codes:
            new_code = self.visit(code)
            if isinstance(new_code, tuple):
                new_codes.extend(new_code)
            elif new_code is None:
                pass
            else:
                assert isinstance(new_code, AHDL_STM) or isinstance(new_code, State)
                new_codes.append(new_code)
        return tuple(new_codes)

    def visit_AHDL_CONST(self, ahdl):
        return ahdl

    def visit_AHDL_OP(self, ahdl):
        args = [self.visit(a) for a in ahdl.args]
        return AHDL_OP(ahdl.op, *args)

    def visit_AHDL_META_OP(self, ahdl):
        args = [self.visit(a) if isinstance(a, AHDL) else a for a in ahdl.args]
        return AHDL_META_OP(ahdl.op, *args)

    def visit_AHDL_VAR(self, ahdl):
        return ahdl

    def visit_AHDL_MEMVAR(self, ahdl):
        return ahdl

    def visit_AHDL_SUBSCRIPT(self, ahdl):
        memvar = self.visit(ahdl.memvar)
        offset = self.visit(ahdl.offset)
        return AHDL_SUBSCRIPT(memvar, offset)

    def visit_AHDL_SYMBOL(self, ahdl):
        return ahdl

    def visit_AHDL_CONCAT(self, ahdl):
        varlist = [self.visit(var) for var in ahdl.varlist]
        return dataclasses.replace(ahdl, varlist=varlist)

    def visit_AHDL_SLICE(self, ahdl):
        var = self.visit(ahdl.var)
        hi = self.visit(ahdl.hi)
        lo = self.visit(ahdl.lo)
        return AHDL_SLICE(var, hi, lo)

    def visit_AHDL_FUNCALL(self, ahdl):
        name = self.visit(ahdl.name)
        args = [self.visit(arg) for arg in ahdl.args]
        return AHDL_FUNCALL(name, tuple(args))

    def visit_AHDL_IF_EXP(self, ahdl):
        cond = self.visit(ahdl.cond)
        lexp = self.visit(ahdl.lexp)
        rexp = self.visit(ahdl.rexp)
        return AHDL_IF_EXP(cond, lexp, rexp)

    def visit_AHDL_BLOCK(self, ahdl):
        codes = self.visit_codes(ahdl.codes)
        return AHDL_BLOCK(ahdl.name, codes)

    def visit_AHDL_NOP(self, ahdl):
        return ahdl

    def visit_AHDL_INLINE(self, ahdl):
        return ahdl

    def visit_AHDL_MOVE(self, ahdl):
        dst = self.visit(ahdl.dst)
        src = self.visit(ahdl.src)
        return AHDL_MOVE(dst, src)

    def visit_AHDL_ASSIGN(self, ahdl):
        dst = self.visit(ahdl.dst)
        src = self.visit(ahdl.src)
        return AHDL_ASSIGN(dst, src)

    def visit_AHDL_FUNCTION(self, ahdl):
        output = self.visit(ahdl.output)
        inputs = tuple([self.visit(inp) for inp in ahdl.inputs])
        stms = tuple([self.visit(stm) for stm in ahdl.stms])
        return AHDL_FUNCTION(output, inputs, stms)

    def visit_AHDL_COMB(self, ahdl):
        stms = tuple([self.visit(stm) for stm in ahdl.stms])
        return AHDL_COMB(ahdl.name, stms)

    def visit_AHDL_EVENT_TASK(self, ahdl):
        stm = self.visit(ahdl.stm)
        return dataclasses.replace(ahdl, stm=stm)

    def visit_AHDL_CONNECT(self, ahdl):
        dst = self.visit(ahdl.dst)
        src = self.visit(ahdl.src)
        return AHDL_CONNECT(dst, src)

    def visit_AHDL_IO_READ(self, ahdl):
        io = self.visit(ahdl.io)
        if ahdl.dst:
            dst = self.visit(ahdl.dst)
        else:
            dst = None
        return AHDL_IO_READ(io, dst, ahdl.is_self)

    def visit_AHDL_IO_WRITE(self, ahdl):
        io = self.visit(ahdl.io)
        src = self.visit(ahdl.src)
        return AHDL_IO_WRITE(io, src, ahdl.is_self)

    def visit_AHDL_SEQ(self, ahdl):
        factor = self.visit(ahdl.factor)
        return dataclasses.replace(ahdl, factor=factor)

    def visit_AHDL_IF(self, ahdl):
        conds = tuple([self.visit(cond) if cond else None for cond in ahdl.conds])
        blocks = tuple([self.visit(block) for block in ahdl.blocks])
        return AHDL_IF(conds, blocks)

    def visit_AHDL_MODULECALL(self, ahdl):
        args = tuple([self.visit(arg) for arg in ahdl.args])
        returns = tuple([self.visit(ret) for ret in ahdl.returns])
        return dataclasses.replace(ahdl, args=args, returns=returns)

    def visit_AHDL_CALLEE_PROLOG(self, ahdl):
        return ahdl

    def visit_AHDL_CALLEE_EPILOG(self, ahdl):
        return ahdl

    def visit_AHDL_PROCCALL(self, ahdl):
        args = tuple([self.visit(arg) for arg in ahdl.args])
        return dataclasses.replace(ahdl, args=args)

    def visit_AHDL_META_WAIT(self, ahdl):
        args = [self.visit(arg) if isinstance(arg, AHDL) else arg for arg in ahdl.args]
        return AHDL_META_WAIT(ahdl.metaid, *args)

    def visit_AHDL_CASE_ITEM(self, ahdl):
        val = self.visit(ahdl.val)
        block = self.visit(ahdl.block)
        return AHDL_CASE_ITEM(val, block)

    def visit_AHDL_CASE(self, ahdl):
        sel = self.visit(ahdl.sel)
        items = tuple([self.visit(item) for item in ahdl.items])
        return AHDL_CASE(sel, items)

    def visit_AHDL_TRANSITION(self, ahdl):
        return ahdl

    def visit_AHDL_TRANSITION_IF(self, ahdl):
        conds = tuple([self.visit(cond) if cond else None for cond in ahdl.conds])
        blocks = tuple([self.visit(block) for block in ahdl.blocks])
        return AHDL_TRANSITION_IF(conds, blocks)

    def visit_AHDL_PIPELINE_GUARD(self, ahdl):
        cond = self.visit(ahdl.conds[0])
        block = self.visit(ahdl.blocks[0])
        return AHDL_PIPELINE_GUARD(cond, block.codes)

    def visit_State(self, state):
        self.current_state = state
        block = self.visit(state.block)
        return dataclasses.replace(state, block=block)

    def visit_PipelineState(self, state):
        self.current_state = state
        block = self.visit(state.block)
        return dataclasses.replace(state, block=block)

    def visit_PipelineStage(self, stage):
        block = self.visit(stage.block)
        return dataclasses.replace(stage, block=block)

    def find_visitor(self, cls):
        method = 'visit_' + cls.__name__
        visitor = getattr(self, method, None)
        if not visitor:
            for base in cls.__bases__:
                visitor = self.find_visitor(base)
                if visitor:
                    break
        return visitor

    def visit(self, ahdl):
        if ahdl.is_a(AHDL_STM):
            self.current_stm = ahdl
        visitor = self.find_visitor(ahdl.__class__)
        new_ahdl = visitor(ahdl)
        if ahdl.is_a(AHDL_STM):
            if id(ahdl) in self.hdlmodule.ahdl2dfgnode:
                _, node = self.hdlmodule.ahdl2dfgnode[id(ahdl)]
                # del self.hdlmodule.ahdl2dfgnode[id(ahdl)]
                if new_ahdl:
                    self.hdlmodule.ahdl2dfgnode[id(new_ahdl)] = (new_ahdl, node)
        return new_ahdl

