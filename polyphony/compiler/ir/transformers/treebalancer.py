from ..ir import BinOp, RelOp, Call, Const, MRef, Array, Temp, CJump, Jump, Move, PolyOp
from ..symbol import Symbol
from logging import getLogger
logger = getLogger(__name__)


class PLURALOP:
    def __init__(self, op):
        self.op = op
        self.values = []

    def __str__(self):
        s = '(PLURALOP ' + self.op + ', '
        s += ', '.join(['(' + str(e) + ',' + str(p) + ')' for e, p in self.values])
        s += ')'
        return s

    def kids(self):
        return self.values

    def eliminate_useless(self):
        for i in range(len(self.values)):
            v = self.values[i]
            if not v:
                continue
            e1, p1 = v
            for j in range(i + 1, len(self.values)):
                v = self.values[j]
                if not v:
                    continue
                e2, p2 = v
                if str(e1) == str(e2) and p1 != p2:
                    logger.debug('eliminate' + str(e1))
                    self.values[i] = None
                    self.values[j] = None
        values = [v for v in self.values if v]
        self.values = values


class TreeBalancer:
    def __init__(self):
        self.done_Blocks = []
        self.b2p = BINOP2PLURALOP()
        self.p2b = PLURALOP2BINOP()

    def process(self, scope):
        for block in scope.traverse_blocks():
            self._process_Block(block)

        for s in scope.children:
            self.process(s)

    def _process_Block(self, block):
        if block not in self.done_Blocks:
            self.block = block
            new_stms = []
            for stm in block.stms:
                self.current_stm = stm
                stm = self.b2p.visit(stm)
                stm = self.p2b.visit(stm)
                new_stms.append(stm)
            block.stms = new_stms

            self.done_Blocks.append(block)
            for succ in block.succs:
                self._process_Block(succ)


class BINOP2PLURALOP:
    def visit_BinOp(self, ir):
        ir.left = self.visit(ir.left)
        ir.right = self.visit(ir.right)
        if ir.op == 'Add' or ir.op == 'Sub':
            newop = PLURALOP('Add')
            polarity = ir.op == 'Add'

            l = ir.left
            if isinstance(l, PLURALOP) and (l.op == 'Add' or l.op == 'Sub'):
                newop.values.extend([e for e in l.kids()])
            else:
                newop.values.append((l, True))

            r = ir.right
            if isinstance(r, PLURALOP) and (r.op == 'Add' or r.op == 'Sub'):
                newop.values.extend([(e, polarity == p) for e, p in r.kids()])
            else:
                newop.values.append((r, polarity))
            return newop
        elif ir.op == 'Mult':
            newop = PLURALOP('Mult')
            polarity = True

            l = ir.left
            if isinstance(l, PLURALOP) and l.op == 'Mult':
                newop.values.extend([e for e in l.kids()])
            else:
                newop.values.append((l, True))

            r = ir.right
            if isinstance(r, PLURALOP) and r.op == 'Mult':
                newop.values.extend([(e, polarity == p) for e, p in r.kids()])
            else:
                newop.values.append((r, polarity))
            return newop
        else:
            newop = PLURALOP(ir.op)
            newop.values.append([(e, True) for e in ir.kids()])
            return newop

    def visit_RelOp(self, ir):
        return ir

    def visit_Call(self, ir):
        return ir

    def visit_Const(self, ir):
        return ir

    def visit_MRef(self, ir):
        return ir

    def visit_Array(self, ir):
        return ir

    def visit_Temp(self, ir):
        return ir

    def visit_CJump(self, ir):
        new_exp = self.visit(ir.exp)
        if new_exp is not ir.exp:
            ir = ir.model_copy(update={'exp': new_exp})
        return ir

    def visit_Jump(self, ir):
        return ir

    def visit_Move(self, ir):
        update = {}
        new_src = self.visit(ir.src)
        if new_src is not ir.src:
            update['src'] = new_src
        new_dst = self.visit(ir.dst)
        if new_dst is not ir.dst:
            update['dst'] = new_dst
        if update:
            ir = ir.model_copy(update=update)
        return ir

    slots = {
        BinOp.__name__: visit_BinOp,
        RelOp.__name__: visit_RelOp,
        Call.__name__: visit_Call,
        Const.__name__: visit_Const,
        MRef.__name__: visit_MRef,
        Array.__name__: visit_Array,
        Temp.__name__: visit_Temp,
        CJump.__name__: visit_CJump,
        Jump.__name__: visit_Jump,
        Move.__name__: visit_Move,
    }

    def visit(self, ir):
        return self.__class__.slots[ir.__class__.__name__](self, ir)


class PLURALOP2BINOP:
    # rebuild tree process uses two FIFO as follows
    #
    #            (outputs)    :    (inputs)
    #step1-1:                 : a, b, c, d, e
    #step1-2: (a,b)           : c, d, e
    #step1-3: (a,b) (c,d)     : e
    #step1-4: (a,b) (c,d) e   :
    #step2-1:                  : (a,b) (c,d) e
    #step2-2: ((a,b), (c,d))   : e
    #step2-3: ((a,b), (c,d)) e :
    #step3-1:                    : ((a,b) (c,d)) e
    #step3-2: (((a,b), (c,d)), e):
    def rebuild_tree(self, op, values):
        #grouping same polarity
        inputs = sorted(values, reverse=True, key=lambda item: str(item[1]))
        #TODO: grouping same bit-width
        #TODO: grouping constants
        return self._rebuild_tree(inputs, op)

    def _rebuild_tree(self, inputs, op):
        #logger.debug([str(e)+str(p) for e, p in inputs])
        if len(inputs) == 1:
            assert inputs[0][1] is True
            return inputs[0][0]

        outputs = []
        while len(inputs):
            #pop one or two item from input, and create binop, then append it to output
            e1, p1 = inputs.pop(0)
            if len(inputs):
                e2, p2 = inputs.pop(0)
                binop = BINOP(self.detectop(op, p1, p2), e1, e2)
                polarity = (p1 and p2) or (p1 and not p2)
                assert (p1 and p2) or (p1 and not p2) or (not p1 and not p2)
                outputs.append((binop, polarity))
            else:
                outputs.append((e1, p1))
        return self._rebuild_tree(outputs, op)

    def detectop(self, op, p1, p2):
        if op == 'Add' and (p1 and not p2):
            return 'Sub'
        else:
            return op

    def visit_PolyOp(self, ir):
        ir.values = [(self.visit(e), p) for e, p in ir.values]
        return self.rebuild_tree(ir.op, ir.values)

    def visit_RelOp(self, ir):
        return ir

    def visit_Call(self, ir):
        return ir

    def visit_Const(self, ir):
        return ir

    def visit_MRef(self, ir):
        return ir

    def visit_Array(self, ir):
        return ir

    def visit_Temp(self, ir):
        return ir

    def visit_CJump(self, ir):
        new_exp = self.visit(ir.exp)
        if new_exp is not ir.exp:
            ir = ir.model_copy(update={'exp': new_exp})
        return ir

    def visit_Jump(self, ir):
        return ir

    def visit_Move(self, ir):
        update = {}
        new_src = self.visit(ir.src)
        if new_src is not ir.src:
            update['src'] = new_src
        new_dst = self.visit(ir.dst)
        if new_dst is not ir.dst:
            update['dst'] = new_dst
        if update:
            ir = ir.model_copy(update=update)
        return ir

    slots = {
        PLURALOP.__name__: visit_PolyOp,
        RelOp.__name__: visit_RelOp,
        Call.__name__: visit_Call,
        Const.__name__: visit_Const,
        MRef.__name__: visit_MRef,
        Array.__name__: visit_Array,
        Temp.__name__: visit_Temp,
        CJump.__name__: visit_CJump,
        Jump.__name__: visit_Jump,
        Move.__name__: visit_Move,
    }

    def visit(self, ir):
        return self.__class__.slots[ir.__class__.__name__](self, ir)


def test():
    a = Symbol.new('a', None)
    b = Symbol.new('b', None)
    c = Symbol.new('c', None)
    # ((a+b)+c) - (b+c)
    ir = BinOp('Sub',
               BinOp('Add',
                     BinOp('Add', Temp(a, ''), Temp(b, '')),
                     Temp(c, '')),
               BinOp('Add', Temp(b, ''), Temp(c, ''))
               )
    #ir = BinOp('Add',
    #           BinOp('Add',
    #                 BinOp('Sub', Temp(a, ''), Temp(b, '')),
    #                 Temp(c, '')),
    #           BinOp('Sub', Temp(c, ''), Temp(b, '')))
    #ir = BinOp('Add',
    #           BinOp('Add',
    #                 BinOp('Add',
    #                       BinOp('Add',
    #                             BinOp('Add', Temp(a, ''), Temp(b, '')),
    #                             Temp(c, '')),
    #                       Temp(a, '')),
    #                 Temp(b, '')),
    #           Temp(c, ''))
    #ir = BinOp('Mult',
    #           BinOp('Mult',
    #                 BinOp('Mult',
    #                       BinOp('Mult',
    #                             BinOp('Mult', Temp(a, ''), Temp(b, '')),
    #                             Temp(c, '')),
    #                       Temp(a, '')),
    #                 Temp(b, '')),
    #           Temp(c, ''))
    #ir = BinOp('Mult',
    #           BinOp('Add',
    #                 BinOp('Sub',
    #                       BinOp('Mult', Temp(c, ''), Temp(c, '')),
    #                       Temp(a, '')),
    #                 Temp(b, '')),
    #           Temp(c, ''))

    logger.debug(str(ir))

    v = BINOP2PLURALOP()
    ir = v.visit(ir)
    logger.debug(str(ir))

    v = PLURALOP2BINOP()
    ir = v.visit(ir)

    logger.debug(str(ir))


if __name__ == '__main__':
    test()
