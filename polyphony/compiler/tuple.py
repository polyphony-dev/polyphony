from .ir import *
from .irvisitor import IRTransformer
from .symbol import Symbol
from .type import Type

class TupleTransformer(IRTransformer):
    def __init__(self):
        super().__init__()

    def process(self, scope):
        super().process(scope)

    def visit_EXPR(self, ir):
        ir.exp = self.visit(ir.exp)
        self.new_stms.append(ir)

    def visit_CJUMP(self, ir):
        ir.exp = self.visit(ir.exp)
        self.new_stms.append(ir)

    def visit_MCJUMP(self, ir):
        for i in range(len(ir.conds)):
            ir.conds[i] = self.visit(ir.conds[i])
        self.new_stms.append(ir)

    def visit_JUMP(self, ir):
        self.new_stms.append(ir)

    def visit_RET(self, ir):
        ir.exp = self.visit(ir.exp)
        self.new_stms.append(ir)

    def _can_direct_unpack(self, lhs, rhs):
        assert len(lhs) == len(rhs)
        def is_contain(ir, irs):
            if not ir.is_a([TEMP, ATTR]):
                return False
            sym = ir.symbol()
            return sym in [ir.symbol() for ir in irs if ir.is_a([TEMP, ATTR])]

        for i, l in enumerate(lhs):
            if is_contain(l, rhs[i+1:]):
                return False
        return True

    def _unpack(self, lhs, rhs):
        assert len(lhs) == len(rhs)
        return [MOVE(dst, src) for dst, src in zip(lhs, rhs)]

    def _make_temp_syms(self, items):
        assert all([item.is_a([TEMP, ATTR]) for item in items])
        return [self.scope.add_temp('{}_{}'.format(Symbol.temp_prefix, item.symbol().name)) for item in items]

    def _make_temps(self, syms, ctx):
        return [TEMP(sym, ctx) for sym in syms]

    def _make_mrefs(self, var, length):
        return [MREF(var.clone(), CONST(i), Ctx.LOAD) for i in range(length)]

    def visit_MOVE(self, ir):
        if ir.dst.is_a(ARRAY):
            assert not ir.dst.is_mutable
            if ir.src.is_a(ARRAY) and not ir.src.is_mutable:
                if self._can_direct_unpack(ir.dst.items, ir.src.items):
                    mvs = self._unpack(ir.dst.items, ir.src.items)
                else:
                    tempsyms = self._make_temp_syms(ir.dst.items)
                    mvs = self._unpack(self._make_temps(tempsyms, Ctx.STORE), ir.src.items)
                    mvs.extend(self._unpack(ir.dst.items, self._make_temps(tempsyms, Ctx.LOAD)))
                for mv in mvs:
                    mv.lineno = ir.lineno
                    mv.dst.lineno = ir.lineno
                    mv.src.lineno = ir.lineno
                    self.new_stms.append(mv)
                return
            elif ir.src.is_a([TEMP, ATTR]) and Type.is_tuple(ir.src.symbol().typ):
                mvs = self._unpack(ir.dst.items, self._make_mrefs(ir.src, len(ir.dst.items)))
                for mv in mvs:
                    mv.lineno = ir.lineno
                    self.new_stms.append(mv)
                return
        else:
            ir.src = self.visit(ir.src)
            ir.dst = self.visit(ir.dst)
        self.new_stms.append(ir)


