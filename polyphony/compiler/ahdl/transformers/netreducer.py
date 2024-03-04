from __future__ import annotations
from typing import TYPE_CHECKING
from ..ahdl import *
from ..ahdltransformer import AHDLTransformer
from logging import getLogger
logger = getLogger(__name__)
if TYPE_CHECKING:
    from ..hdlmodule import HDLModule


AssignVar = AHDL_VAR | AHDL_SUBSCRIPT

class NetReducer(AHDLTransformer):
    def process(self, hdlmodule: HDLModule):
        self.hdlmodule = hdlmodule
        while self._eliminate_simple_assign():
            pass
        while self._eliminate_common_assign_src():
            pass

    def _rvalue_from_dst(self, assign_dst: AssignVar) -> AssignVar:
        if isinstance(assign_dst, AHDL_VAR):
            dst = AHDL_VAR(assign_dst.vars, Ctx.LOAD)
        elif isinstance(assign_dst, AHDL_SUBSCRIPT):
            dst = AHDL_SUBSCRIPT(AHDL_VAR(assign_dst.memvar.vars, Ctx.LOAD), assign_dst.offset)
        else:
            assert False
        return dst

    def _get_signal(self, var):
        if isinstance(var, AHDL_VAR):
            return var.sig
        elif isinstance(var, AHDL_SUBSCRIPT):
            return var.memvar.sig
        else:
            assert False

    def _eliminate_simple_assign(self):
        self.var_map: dict[AssignVar, AssignVar] = {}
        assigns = self.hdlmodule.get_static_assignment()
        for assign in assigns:
            if not isinstance(assign.src, (AHDL_VAR, AHDL_SUBSCRIPT)):
                continue
            # If key (variable to be replaced) appears in map.values(),
            # the variable in map.values() must also be replaced.
            # Therefore, to avoid substitutions in map.values(),
            # the creation of map is stopped here and such variable
            # substitutions are carried over to the next time.
            dst = self._rvalue_from_dst(assign.dst)
            ks = set(self.var_map.keys())
            ks |= set((dst,))
            vs = set(assign.src.find_ahdls(AHDL_VAR))
            for v in self.var_map.values():
                vs |= set(v.find_ahdls(AHDL_VAR))
            if vs & ks:
                break
            # We can't replace a variable with a different width or sign.
            dst_sig = self._get_signal(dst)
            src_sig = self._get_signal(assign.src)
            if dst_sig.width != src_sig.width or dst_sig.is_int() != src_sig.is_int():
                continue
            self.var_map[dst] = assign.src
        if not self.var_map:
            return False
        for k, v in self.var_map.items():
            logger.debug(f'{k} -> {v}')
        return self._replace_var()

    def _eliminate_common_assign_src(self):
        assign_map: dict[AHDL_EXP, AssignVar] = {}
        self.var_map: dict[AssignVar, AssignVar] = {}
        assigns = self.hdlmodule.get_static_assignment()
        for assign in assigns:
            if isinstance(assign.src, AHDL_CONST):
                continue
            if assign.src in assign_map:
                main_var = assign_map[assign.src]
                dst = self._rvalue_from_dst(assign.dst)
                assert dst not in self.var_map
                self.var_map[dst] = main_var
            else:
                main_var = self._rvalue_from_dst(assign.dst)
                assign_map[assign.src] = main_var
        if not self.var_map:
            return False
        for k, v in self.var_map.items():
            logger.debug(f'{k} -> {v}')
        return self._replace_var()

    def _replace_var(self):
        # replace vars in assignments
        new_decls = []
        self.replaced_ahdls = []
        for decl in self.hdlmodule.decls:
            new_decl = self.visit(decl)
            new_decls.append(new_decl)
        self.hdlmodule.decls = new_decls
        # replace vars in tasks
        new_tasks = []
        for task in self.hdlmodule.tasks:
            new_task = self.visit(task)
            new_tasks.append(new_task)
        self.hdlmodule.tasks = new_tasks

        if len(self.replaced_ahdls) == 0:
            return False

        # remove replaced decls and signals
        assigns = self.hdlmodule.get_static_assignment()
        for assign in assigns:
            key = str(assign.dst)
            if key in self.replaced_ahdls:
                self.hdlmodule.remove_decl(assign)
                if key in self.hdlmodule.signals:
                    self.hdlmodule.remove_sig(key)
        return True

    def visit_AHDL_VAR(self, ahdl):
        key = ahdl
        if key in self.var_map:
            self.replaced_ahdls.append(str(ahdl))
            logger.debug(f'replace: {self.current_stm}  [[{key} -> {self.var_map[key]}]]')
            return self.var_map[key]
        return ahdl

    def visit_AHDL_SUBSCRIPT(self, ahdl):
        memvar = self.visit(ahdl.memvar)
        offset = self.visit(ahdl.offset)
        ahdl = AHDL_SUBSCRIPT(memvar, offset)
        key = ahdl
        if key in self.var_map:
            self.replaced_ahdls.append(str(ahdl))
            logger.debug(f'replace: {self.current_stm}  [[{key} -> {self.var_map[key]}]]')
            return self.var_map[key]
        return ahdl
