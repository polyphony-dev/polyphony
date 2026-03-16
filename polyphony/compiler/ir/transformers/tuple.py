"""TupleTransformer using new IR (ir.py)."""
from ..ir import (
    IrVariable, Array, Move, Expr, CJump, MCJump, Jump, Ret,
    Temp, MRef, Const, Call, Ctx,
)
from ..ir_visitor import IrTransformer
from ..ir_helper import irexp_type
from ..symbol import Symbol


class NewTupleTransformer(IrTransformer):
    def visit_Expr(self, ir):
        ir.exp = self.visit(ir.exp)
        self.new_stms.append(ir)

    def visit_CJump(self, ir):
        ir.exp = self.visit(ir.exp)
        self.new_stms.append(ir)

    def visit_MCJump(self, ir):
        for i in range(len(ir.conds)):
            ir.conds[i] = self.visit(ir.conds[i])
        self.new_stms.append(ir)

    def visit_Jump(self, ir):
        self.new_stms.append(ir)

    def visit_Ret(self, ir):
        ir.exp = self.visit(ir.exp)
        self.new_stms.append(ir)

    def _can_direct_unpack(self, lhs, rhs):
        assert len(lhs) == len(rhs)

        def is_contain(ir, irs):
            if not isinstance(ir, IrVariable):
                return False
            return ir.name in [x.name for x in irs if isinstance(x, IrVariable)]

        for i, l in enumerate(lhs):
            if is_contain(l, rhs[i + 1:]):
                return False
        return True

    def _unpack(self, lhs, rhs):
        assert len(lhs) == len(rhs)
        return [Move(dst=dst, src=src) for dst, src in zip(lhs, rhs)]

    def _make_temp_syms(self, items):
        assert all(isinstance(item, IrVariable) for item in items)
        return [self.scope.add_temp('{}_{}'.format(Symbol.temp_prefix, item.name)) for item in items]

    def _make_temps(self, syms, ctx):
        return [Temp(name=sym.name, ctx=ctx) for sym in syms]

    def _make_mrefs(self, var, length):
        return [MRef(mem=var.model_copy(deep=True), offset=Const(value=i), ctx=Ctx.LOAD) for i in range(length)]

    def visit_Move(self, ir):
        if isinstance(ir.dst, Array):
            assert not ir.dst.is_mutable
            if isinstance(ir.src, Array) and not ir.src.is_mutable:
                if self._can_direct_unpack(ir.dst.items, ir.src.items):
                    mvs = self._unpack(ir.dst.items, ir.src.items)
                else:
                    tempsyms = self._make_temp_syms(ir.dst.items)
                    mvs = self._unpack(self._make_temps(tempsyms, Ctx.STORE), ir.src.items)
                    mvs.extend(self._unpack(ir.dst.items, self._make_temps(tempsyms, Ctx.LOAD)))
                for mv in mvs:
                    mv.loc = ir.loc
                    self.new_stms.append(mv)
                return
            elif isinstance(ir.src, IrVariable) and irexp_type(ir.src, self.scope).is_tuple():
                mvs = self._unpack(ir.dst.items, self._make_mrefs(ir.src, len(ir.dst.items)))
                for mv in mvs:
                    mv.loc = ir.loc
                    self.new_stms.append(mv)
                return
            elif isinstance(ir.src, Call) and self.scope.is_testbench():
                raise NotImplementedError('Return of sequence type value is not implemented')
        else:
            ir.src = self.visit(ir.src)
            ir.dst = self.visit(ir.dst)
        self.new_stms.append(ir)
