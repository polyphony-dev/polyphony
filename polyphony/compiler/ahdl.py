from .signal import Signal
from .ir import Ctx
from .memref import MemRefNode

PYTHON_OP_2_HDL_OP_MAP = {
    'And':'&&',
    'Or':'||',
    'Add':'+',
    'Sub':'-',
    'Mult':'*',
    'Div':'/',
    'LShift':'<<',
    'RShift':'>>',
    'BitOr':'|',
    'BitXor':'^',
    'BitAnd':'&',
    'Eq':'==',
    'NotEq':'!=',
    'Lt':'<',
    'LtE':'<=',
    'Gt':'>',
    'GtE':'>=',
    'IsNot':'!=',
    'USub':'-',
    'UAdd':'+',
    'Not':'!',
    'Invert':'~'
    }

#Abstract HDL
class AHDL:
    def __init__(self):
        pass

    def is_a(self, cls):
        if isinstance(cls, list) or isinstance(cls, tuple):
            for c in cls:
                if isinstance(self, c):
                    return True
            return False
        else:
            return isinstance(self, cls)

    def __repr__(self):
        return self.__str__()

class AHDL_CONST(AHDL):
    def __init__(self, value):
        super().__init__()
        self.value = value

    def __str__(self):
        return '{}'.format(self.value)

class AHDL_OP(AHDL):
    def __init__(self, op, left, right):
        super().__init__()
        self.op = op
        self.left = left
        self.right = right

    def __str__(self):
        if self.right:
            return '({} {} {})'.format(self.left, PYTHON_OP_2_HDL_OP_MAP[self.op], self.right)
        else:
            return '({}{})'.format(PYTHON_OP_2_HDL_OP_MAP[self.op], self.left)

class AHDL_VAR(AHDL):
    def __init__(self, sig, ctx):
        assert sig and isinstance(sig, Signal)
        super().__init__()
        self.sig = sig
        self.ctx = ctx

    def __str__(self):
         return '{}'.format(self.sig)

class AHDL_MEMVAR(AHDL):
    def __init__(self, memnode, ctx):
        assert memnode and isinstance(memnode, MemRefNode)
        super().__init__()
        self.memnode = memnode
        self.ctx = ctx

    def __str__(self):
        return '{}'.format(self.memnode.sym.name)

class AHDL_SYMBOL(AHDL):
    def __init__(self, name):
        assert name and isinstance(name, str)
        super().__init__()
        self.name = name

    def __str__(self):
         return '{}'.format(self.name)

class AHDL_CONCAT(AHDL):
    def __init__(self, varlist):
        super().__init__()
        self.varlist = varlist

    def __str__(self):
        return '{{{0}}}'.format(', '.join([str(v) for v in self.varlist]))
    
class AHDL_NOP(AHDL):
    def __init__(self, info):
        super().__init__()
        self.info = info

    def __str__(self):
        return 'nop for {}'.format(self.info)

class AHDL_MOVE(AHDL):
    def __init__(self, dst, src):
        assert dst.is_a(AHDL)
        assert src.is_a(AHDL)
        if src.is_a(AHDL_VAR):
            assert src.ctx == Ctx.LOAD
        if dst.is_a(AHDL_VAR):
            assert dst.ctx == Ctx.STORE
        super().__init__()
        self.dst = dst
        self.src = src

    def __str__(self):
        return '{} <= {}'.format(self.dst, self.src)

class AHDL_ASSIGN(AHDL):
    def __init__(self, dst, src):
        assert dst.is_a(AHDL)
        assert src.is_a(AHDL)
        super().__init__()
        self.dst = dst
        self.src = src

    def __str__(self):
        return '{} := {}'.format(self.dst, self.src)

class AHDL_CONNECT(AHDL):
    def __init__(self, dst, src):
        assert dst.is_a(AHDL)
        assert src.is_a(AHDL)
        super().__init__()
        self.dst = dst
        self.src = src

    def __str__(self):
        return '{} = {}'.format(self.dst, self.src)

class AHDL_MEM(AHDL):
    def __init__(self, name, offset):
        super().__init__()
        self.name = name
        self.offset = offset

    def __str__(self):
        return '{}[{}]'.format(self.name, self.offset)

class AHDL_STORE(AHDL):
    def __init__(self, mem, src):
        super().__init__()
        self.mem = mem
        self.src = src

    def __str__(self):
        return '{} <= {}'.format(self.mem, self.src)

class AHDL_LOAD(AHDL):
    def __init__(self, dst, mem):
        super().__init__()
        self.dst = dst
        self.mem = mem

    def __str__(self):
        return '{} <= {}'.format(self.dst, self.mem)

   

# ([cond], [code]) => if (cond) code
# ([cond, None], [code1, code2]) => if (cond) code1 else code2

class AHDL_IF(AHDL):
    def __init__(self, conds, codes_list):
        super().__init__()
        self.conds = conds
        self.codes_list = codes_list
        assert len(conds) == len(codes_list)
        assert conds[0]

    def __str__(self):
        s = 'if {}\n'.format(self.conds[0])
        for code in self.codes_list[0]:
            s += '    {}\n'.format(code)
        for cond, codes in zip(self.conds[1:], self.codes_list[1:]):
            if cond:
                s += '  elif {}\n'.format(cond)
                for code in codes:
                    s += '    {}\n'.format(code)
            else:
                s += '  else\n'
                for code in self.codes_list[-1]:
                    s += '    {}'.format(code)
        return s

class AHDL_IF_EXP(AHDL):
    def __init__(self, cond, lexp, rexp):
        super().__init__()
        self.cond = cond
        self.lexp = lexp
        self.rexp = rexp

    def __str__(self):
        return '{} ? {} : {}\n'.format(self.cond, self.lexp, self.rexp)

class AHDL_FUNCALL(AHDL):
    def __init__(self, name, args):
        assert isinstance(name, str)
        super().__init__()
        self.name = name
        self.args = args

    def __str__(self):
        return '{}({})'.format(self.name, ', '.join([str(arg) for arg in self.args]))

class AHDL_PROCCALL(AHDL):
    def __init__(self, name, args):
        assert isinstance(name, str)
        super().__init__()
        self.name = name
        self.args = args

    def __str__(self):
        return '{}({})'.format(self.name, ', '.join([str(arg) for arg in self.args]))

class AHDL_META(AHDL):
    def __init__(self, *args):
        super().__init__()
        self.metaid = args[0]
        self.args = args[1:]

    def __str__(self):
        return '{}({})'.format(self.metaid, ', '.join([str(arg) for arg in self.args]))

class AHDL_FUNCTION(AHDL):
    def __init__(self, output, inputs, stms):
        super().__init__()
        self.inputs = inputs
        self.output = output
        self.stms = stms

    def __str__(self):
        return 'function {}'.format(self.name)


class AHDL_MUX(AHDL):
    def __init__(self, name, selector, inputs, output):
        super().__init__()
        assert isinstance(name, str)
        assert isinstance(output, Signal)
        self.name = name
        self.selector = selector
        self.inputs = inputs
        self.output = output

    def __str__(self):
        return 'MUX {}'.format(self.name)


class AHDL_DEMUX(AHDL):
    def __init__(self, name, selector, input, outputs):
        super().__init__()
        assert isinstance(name, str)
        assert isinstance(input, Signal)
        self.name = name
        self.selector = selector
        self.input = input
        self.outputs = outputs

    def __str__(self):
        return 'DEMUX {}'.format(self.name)


class AHDL_COMB(AHDL):
    def __init__(self, name, stms):
        super().__init__()
        assert isinstance(name, str)
        self.name = name
        self.stms = stms

    def __str__(self):
        return 'COMB {}'.format(self.name)


class AHDL_CASE(AHDL):
    def __init__(self, sel, items):
        super().__init__()
        self.sel = sel
        self.items = items

    def __str__(self):
        return 'case' + ', '.join([str(item) for item in self.items])


class AHDL_CASE_ITEM(AHDL):
    def __init__(self, val, stm):
        super().__init__()
        self.val = val
        self.stm = stm

    def __str__(self):
        return '{}:{}'.format(self.val, str(self.stm))
