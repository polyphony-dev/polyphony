from collections import defaultdict, deque
from .ahdl import AHDL_CONST, AHDL_VAR, AHDL_MOVE, AHDL_IF, AHDL_META
from logging import getLogger
logger = getLogger(__name__)

class STGOptimizer():
    def __init__(self):
        self.stg_return_state = {}

    def process(self, scope):
        if scope.is_class():
            return
        self.scope = scope
        self._concat_stgs()
        self._remove_unused_state()

        #usedef = STGUseDefDetector()
        #usedef.process(scope)
        #usedef.table.dump()

        # all_vars = usedef.table.get_all_vars()
        # for var in all_vars:
        #     if var.sym.ancestor:
        #         if not var.sym.is_condition():
        #             logger.debug('back to ancestor : ' + str(var.sym) + ' = ' + str(var.sym.ancestor))
        #             var.sym = var.sym.ancestor

        self._remove_move()
        self._remove_empty_state()
        if not scope.is_testbench():
            self._move_valid()

    def _concat_stgs(self):
        for stg in self.scope.stgs:
            for i, state in enumerate(stg.states()):
                self._process_concat_state(state)

    def _process_concat_state(self, state):
        remove_codes = []
        for code in state.codes:
            if isinstance(code, AHDL_META):
                if code.metaid == 'STG_JUMP':
                    stg_name = code.args[0]
                    stg = self.scope.find_stg(stg_name)
                    target_state = stg.init_state
                    _, ret_state, _ = state.next_states[0]
                    self.stg_return_state[stg_name] = ret_state
                    
                    state.clear_next()
                    state.set_next((AHDL_CONST(1), target_state, None))
                    remove_codes.append(code)
                elif code.metaid == 'STG_EXIT':
                    top = self.scope.stgs[0]
                    state.clear_next()
                    state.set_next((AHDL_CONST(1), top.finish_state, None))
                    remove_codes.append(code)
        for code in remove_codes:
            state.codes.remove(code)

        #add the state transition to a state in the other stg
        stg = state.stg
        if not state.next_states:
            return
        cond1, nstate1, _ = state.next_states[0]
        if cond1 is None or cond1.is_a(AHDL_CONST):
            if state is stg.finish_state and stg.name in self.stg_return_state:
                ret_state = self.stg_return_state[stg.name]
                #replace return state
                state.clear_next()
                state.set_next((AHDL_CONST(1), ret_state, None))

    def _remove_unused_state(self):
        for stg in self.scope.stgs:
            self._remove_unused(stg)

    def _remove_unused(self, stg):
        worklist = deque()
        worklist.append(stg.init_state.group)
        used_groups = set()
        while worklist:
            grp = worklist.pop()
            if grp in used_groups:
                continue
            used_groups.add(grp)
            for state in grp.states:
                for cond, s, _ in state.next_states:
                    if cond and cond.is_a(AHDL_CONST) and cond.value == 1:
                        worklist.append(s.group)
                        # skip others
                        break
                    else:
                        worklist.append(s.group)

        for unused in set(stg.groups.values()).difference(used_groups):
            print('remove '  + unused.name)
            del stg.groups[unused.name]


    def _remove_move(self):
        for stg in self.scope.stgs:
            for state in stg.states():
                self._process_remove_move_state(state)

    def _process_remove_move_state(self, state):
        remove_mv = []
        for code in state.codes:
            if code.is_a(AHDL_MOVE):
                mv = code
                if mv.src.is_a(AHDL_VAR) and mv.dst.is_a(AHDL_VAR):
                    if mv.src.sig is mv.dst.sig:
                        remove_mv.append(mv)
        for mv in remove_mv:
            state.codes.remove(mv)


    def _remove_empty_state(self):
        for stg in self.scope.stgs:
            empty_states = []
            for state in stg.states():
                if not state.codes:
                    cond, _, codes = state.next_states[0]
                    if cond is None or cond.is_a(AHDL_CONST):
                        self.disconnect_state(state)
                        empty_states.append(state)
            for s in empty_states:
                stg.remove_state(s)

    def disconnect_state(self, state):
        _, nstate, _ = state.next_states[0]
        nstate.prev_states.remove(state)

        for prev in state.prev_states:
            prev.replace_next(state, nstate)
            nstate.set_prev(prev)

    def _move_valid(self):
        for stg in self.scope.stgs:
            if stg.finish_state.codes:
                assert len(stg.finish_state.codes) == 1
                set_valid = stg.finish_state.codes[0]
                for prev in stg.finish_state.prev_states:
                    if len(prev.next_states) == 1:
                        assert prev.next_states[0][1] is stg.finish_state
                        if set_valid not in prev.codes:
                            prev.codes.append(set_valid)
                    else:
                        for _, nstate, codes in prev.next_states:
                            if nstate is stg.finish_state and set_valid not in prev.codes:
                                codes.append(set_valid)
                stg.finish_state.codes = []

class STGUseDefTable:
    def __init__(self):
        self._sig_defs_stm = defaultdict(set)
        self._sig_uses_stm = defaultdict(set)
        self._var_defs_stm = defaultdict(set)
        self._var_uses_stm = defaultdict(set)

    def add_var_def(self, var, stm):
        self._sig_defs_stm[var.sig].add(stm)
        self._var_defs_stm[var].add(stm)

    def remove_var_def(self, var, stm):
        self._sig_defs_stm[var.sig].discard(stm)
        self._var_defs_stm[var].discard(stm)

    def add_var_use(self, var, stm):
        self._sig_uses_stm[var.sig].add(stm)
        self._var_uses_stm[var].add(stm)

    def remove_var_use(self, var, stm):
        self._sig_uses_stm[var.sig].discard(stm)
        self._var_uses_stm[var].discard(stm)

    def get_all_vars(self):
        def_stm = self._var_defs_stm
        vs = list(def_stm.keys())
        use_stm = self._var_uses_stm
        vs.extend(use_stm.keys())
        return vs

    def dump(self):
        logger.debug('statements that has symbol defs')
        for sig, stms in self._sig_defs_stm.items():
            logger.debug(sig)
            for stm in stms:
                logger.debug('    ' + str(stm))

        logger.debug('statements that has symbol uses')
        for sig, stms in self._sig_uses_stm.items():
            logger.debug(sig)
            for stm in stms:
                logger.debug('    ' + str(stm))


class STGUseDefDetector():
    def __init__(self):
        super().__init__()
        self.table = STGUseDefTable()

    def process(self, scope):
        for stg in scope.stgs:
            for i, state in enumerate(stg.states()):
                self._process_State(state)

    def _process_State(self, state):
        for code in state.codes:
            self.current_stm = code
            self.visit(code)

        for _, _, codes in state.next_states:
            if codes:
                for code in codes:
                    self.current_stm = code
                    self.visit(code)

    def visit_AHDL_CONST(self, ahdl):
        pass

    def visit_AHDL_VAR(self, ahdl):
        pass

    def visit_AHDL_OP(self, ahdl):
        if ahdl.left.is_a(AHDL_VAR):
            self.table.add_var_use(ahdl.left, self.current_stm)
        else:
            self.visit(ahdl.left)

        if ahdl.right:
            if ahdl.right.is_a(AHDL_VAR):
                self.table.add_var_use(ahdl.right, self.current_stm)
            else:
                self.visit(ahdl.right)
            
    def visit_AHDL_MEM(self, ahdl):
        pass

    def visit_AHDL_NOP(self, ahdl):
        pass

    def visit_AHDL_MOVE(self, ahdl):
        if ahdl.src.is_a(AHDL_VAR):
            self.table.add_var_use(ahdl.src, self.current_stm)
        else:
            self.visit(ahdl.src)

        if ahdl.dst.is_a(AHDL_VAR):
            self.table.add_var_def(ahdl.dst, self.current_stm)
        else:
            self.visit(ahdl.dst)

    def visit_AHDL_STORE(self, ahdl):
        if ahdl.src.is_a(AHDL_VAR):
            self.table.add_var_use(ahdl.src, self.current_stm)
        else:
            self.visit(ahdl.src)

    def visit_AHDL_LOAD(self, ahdl):
        if ahdl.dst.is_a(AHDL_VAR):
            self.table.add_var_def(ahdl.dst, self.current_stm)
        else:
            self.visit(ahdl.dst)

    def visit_AHDL_IF(self, ahdl):
        
        for cond, codes in zip(ahdl.conds, ahdl.codes_list):
            self.current_stm = ahdl
            if cond.is_a(AHDL_VAR):
                self.table.add_var_use(cond, ahdl)
            else:
                self.visit(cond)

            for code in codes:
                self.current_stm = code
                self.visit(code)

    def visit_AHDL_FUNCALL(self, ahdl):
        for arg in ahdl.args:
            if arg.is_a(AHDL_VAR):
                self.table.add_var_use(arg, self.current_stm)
            else:
                self.visit(arg)


    def visit_AHDL_PROCCALL(self, ahdl):
        for arg in ahdl.args:
            if arg.is_a(AHDL_VAR):
                self.table.add_var_use(arg, self.current_stm)
            else:
                self.visit(arg)

    def visit_AHDL_META(self, ahdl):
        pass

    def visit(self, ahdl):
        method = 'visit_' + ahdl.__class__.__name__
        visitor = getattr(self, method, None)
        return visitor(ahdl)



