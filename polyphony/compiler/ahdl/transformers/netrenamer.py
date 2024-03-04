from __future__ import annotations
from collections import deque
import dataclasses
from typing import TYPE_CHECKING
from ..ahdl import *
from ..ahdltransformer import AHDLTransformer
from ..ahdlvisitor import AHDLVisitor
from ...common.env import env
from logging import getLogger
logger = getLogger(__name__)
if TYPE_CHECKING:
    from ..hdlmodule import HDLModule


PYTHON_OP_2_OP_MAP = {
    'And': 'and', 'Or': 'or',
    'Add': 'add', 'Sub': 'sub', 'Mult': 'mul', 'FloorDiv': 'div', 'Mod': 'mod',
    'LShift': 'lsh', 'RShift': 'rsh',
    'BitOr': 'bor', 'BitXor': 'xor', 'BitAnd': 'band',
    'Eq': 'eq', 'NotEq': 'ne', 'Lt': 'lt', 'LtE': 'le', 'Gt': 'gt', 'GtE': 'ge',
    'Is': 'eq', 'IsNot': 'ne',
    'USub': 'minus', 'UAdd': 'plus', 'Not': 'not', 'Invert': 'inv'
}

AssignVar = AHDL_VAR | AHDL_SUBSCRIPT

class AHDLRenameVisitor(AHDLVisitor):
    def visit_AHDL_CONST(self, ahdl):
        if isinstance(ahdl.value, int) and ahdl.value < 0:
            return f'minus_{abs(ahdl.value)}'
        return str(ahdl)

    def visit_AHDL_VAR(self, ahdl):
        if ahdl.sig.is_field() or ahdl.sig.is_connector():
            return str(ahdl)
        return None

    def visit_AHDL_OP(self, ahdl):
        if len(ahdl.args) == 1:
            s_arg = self.visit(ahdl.args[0])
            if not s_arg:
                return None
            return f'{PYTHON_OP_2_OP_MAP[ahdl.op]}_{s_arg}'
        elif len(ahdl.args) == 2:
            s_arg0 = self.visit(ahdl.args[0])
            if not s_arg0:
                return None
            s_arg1 = self.visit(ahdl.args[1])
            if not s_arg1:
                return None
            return f'{s_arg0}_{PYTHON_OP_2_OP_MAP[ahdl.op]}_{s_arg1}'
        return None


class NetRenamer(object):
    def process(self, hdlmodule: HDLModule):
        self.hdlmodule = hdlmodule
        self._rename_net()

    def _rename_net(self):
        renamer = AHDLRenameVisitor()
        assigns = self.hdlmodule.get_static_assignment()
        for assign in assigns:
            if isinstance(assign.src, (AHDL_CONST, AHDL_VAR)):
                continue
            name = renamer.visit(assign.src)
            if not name:
                continue
            if isinstance(assign.dst, AHDL_VAR):
                assign.dst.sig.name = name.replace('.', '_')
