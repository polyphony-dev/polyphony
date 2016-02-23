from .ir import BINOP, RELOP, CALL, CONST, MREF, ARRAY, TEMP, CJUMP, JUMP, MOVE
from .symbol import Symbol
from logging import getLogger
logger = getLogger(__name__)

class PLURALOP:
    def __init__(self, op):
        self.op = op
        self.values = []

    def __str__(self):
        s = '(PLURALOP ' + self.op + ', '
        s += ', '.join(['('+str(e)+','+str(p)+')' for e, p in self.values])
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
            for j in range(i+1, len(self.values)):
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
        for block in scope.blocks:
            self._process_Block(block)

        for s in scope.children:
            self.process(s)

    def _process_Block(self, block):
        if block not in self.done_Blocks:
            self.block = block
            for stm in block.stms:
                self.current_stm = stm
                self.b2p.visit(stm)
                self.p2b.visit(stm)

            self.done_Blocks.append(block)
            for succ in block.succs:
                self._process_Block(succ)

class BINOP2PLURALOP:
    def visit_BINOP(self, ir):
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
                newop.values.extend([(e, polarity==p) for e, p in r.kids()])
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
                newop.values.extend([(e, polarity==p) for e, p in r.kids()])
            else:
                newop.values.append((r, polarity))
            return newop
        else:
            newop = PLURALOP(ir.op)
            newop.values.append([(e, True) for e in ir.kids()])
            return newop

    def visit_RELOP(self, ir):
        return ir

    def visit_CALL(self, ir):
        return ir

    def visit_CONST(self, ir):
        return ir

    def visit_MREF(self, ir):
        return ir

    def visit_ARRAY(self, ir):
        return ir

    def visit_TEMP(self, ir):
        return ir

    def visit_CJUMP(self, ir):
        ir.exp = self.visit(ir.exp)

    def visit_JUMP(self, ir):
        pass

    def visit_MOVE(self, ir):
        ir.src = self.visit(ir.src)
        ir.dst = self.visit(ir.dst)

    slots = {
        BINOP.__name__:visit_BINOP,
        RELOP.__name__:visit_RELOP,
        CALL.__name__:visit_CALL,
        CONST.__name__:visit_CONST,
        MREF.__name__:visit_MREF,
        ARRAY.__name__:visit_ARRAY,
        TEMP.__name__:visit_TEMP,
        CJUMP.__name__:visit_CJUMP,
        JUMP.__name__:visit_JUMP,
        MOVE.__name__:visit_MOVE
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
        outputs = []
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


    def visit_PLURALOP(self, ir):
        ir.values = [(self.visit(e), p) for e, p in ir.values]
        return self.rebuild_tree(ir.op, ir.values)

    def visit_RELOP(self, ir):
        return ir

    def visit_CALL(self, ir):
        return ir

    def visit_CONST(self, ir):
        return ir

    def visit_MREF(self, ir):
        return ir

    def visit_ARRAY(self, ir):
        return ir

    def visit_TEMP(self, ir):
        return ir

    def visit_CJUMP(self, ir):
        ir.exp = self.visit(ir.exp)

    def visit_JUMP(self, ir):
        pass

    def visit_MOVE(self, ir):
        ir.src = self.visit(ir.src)
        ir.dst = self.visit(ir.dst)

    slots = {
        PLURALOP.__name__:visit_PLURALOP,
        RELOP.__name__:visit_RELOP,
        CALL.__name__:visit_CALL,
        CONST.__name__:visit_CONST,
        MREF.__name__:visit_MREF,
        ARRAY.__name__:visit_ARRAY,
        TEMP.__name__:visit_TEMP,
        CJUMP.__name__:visit_CJUMP,
        JUMP.__name__:visit_JUMP,
        MOVE.__name__:visit_MOVE
    }

    def visit(self, ir):
        return self.__class__.slots[ir.__class__.__name__](self, ir)


def test():
    a = Symbol.new('a', None)
    b = Symbol.new('b', None)
    c = Symbol.new('c', None)
    # ((a+b)+c) - (b+c)
    ir = BINOP('Sub', 
               BINOP('Add', 
                     BINOP('Add', TEMP(a, ''), TEMP(b, '')), 
                     TEMP(c, '')),
               BINOP('Add', TEMP(b, ''), TEMP(c, ''))
               )
    #ir = BINOP('Add', BINOP('Add', BINOP('Sub', TEMP(a, ''), TEMP(b, '')), TEMP(c, '')), BINOP('Sub', TEMP(c, ''), TEMP(b, '')))
    #ir = BINOP('Add', BINOP('Add', BINOP('Add', BINOP('Add', BINOP('Add', TEMP(a, ''), TEMP(b, '')), TEMP(c, '')), TEMP(a, '')), TEMP(b, '')), TEMP(c, ''))
    #ir = BINOP('Mult', BINOP('Mult', BINOP('Mult', BINOP('Mult', BINOP('Mult', TEMP(a, ''), TEMP(b, '')), TEMP(c, '')), TEMP(a, '')), TEMP(b, '')), TEMP(c, ''))
    #ir = BINOP('Mult', BINOP('Add', BINOP('Sub', BINOP('Mult', TEMP(c, ''), TEMP(c, '')), TEMP(a, '')), TEMP(b, '')), TEMP(c, ''))

    logger.debug(str(ir))

    v = BINOP2PLURALOP()
    ir = v.visit(ir)
    logger.debug(str(ir))
    
    v = PLURALOP2BINOP()
    ir = v.visit(ir)
    
    logger.debug(str(ir))

if __name__ == '__main__':
    test()
