from collections import defaultdict
from .signal import Signal
from .ir import Ctx
from .memref import MemRefNode, MemParamNode
from .utils import is_a

PYTHON_OP_2_HDL_OP_MAP = {
    'And':'&&',
    'Or':'||',
    'Add':'+',
    'Sub':'-',
    'Mult':'*',
    'FloorDiv':'//',
    'Mod':'%',
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
        return is_a(self, cls)

    def __repr__(self):
        return self.__str__()

class AHDL_EXP(AHDL):
    pass

class AHDL_CONST(AHDL_EXP):
    def __init__(self, value):
        super().__init__()
        self.value = value

    def __str__(self):
        return '{}'.format(self.value)

class AHDL_OP(AHDL_EXP):
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

class AHDL_VAR(AHDL_EXP):
    def __init__(self, sig, ctx):
        assert sig and isinstance(sig, Signal)
        super().__init__()
        self.sig = sig
        self.ctx = ctx

    def __str__(self):
         return '{}'.format(self.sig)

class AHDL_MEMVAR(AHDL_EXP):
    def __init__(self, sig, memnode, ctx):
        assert sig and isinstance(sig, Signal)
        assert memnode
        assert (isinstance(memnode, MemRefNode) or isinstance(memnode, MemParamNode))
        super().__init__()
        self.sig = sig
        self.memnode = memnode
        self.ctx = ctx

    def __str__(self):
        return '{}[]'.format(self.sig)

    def name(self):
        return self.sig.name

class AHDL_SUBSCRIPT(AHDL_EXP):
    def __init__(self, memvar, offset):
        assert memvar.is_a(AHDL_MEMVAR)
        assert offset.is_a(AHDL_EXP)
        super().__init__()
        self.memvar = memvar
        self.offset = offset

    def __str__(self):
        return '{}[{}]'.format(self.memvar.name(), self.offset)

class AHDL_SYMBOL(AHDL_EXP):
    def __init__(self, name):
        assert name and isinstance(name, str)
        super().__init__()
        self.name = name

    def __str__(self):
         return '{}'.format(self.name)

class AHDL_CONCAT(AHDL_EXP):
    def __init__(self, varlist, op=None):
        super().__init__()
        assert isinstance(varlist, list)
        self.varlist = varlist
        self.op = op

    def __str__(self):
        if self.op:
            return '{{{0}}}'.format(PYTHON_OP_2_HDL_OP_MAP[self.op].join([str(v) for v in self.varlist]))
        else:
            return '{{{0}}}'.format(', '.join([str(v) for v in self.varlist]))
        
class AHDL_NOP(AHDL_EXP):
    def __init__(self, info):
        super().__init__()
        self.info = info

    def __str__(self):
        return 'nop for {}'.format(self.info)

class AHDL_STM(AHDL):
    pass

class AHDL_MOVE(AHDL_STM):
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

class AHDL_DECL(AHDL):
    pass

class AHDL_SIGNAL_DECL(AHDL_DECL):
    pass

class AHDL_REG_DECL(AHDL_SIGNAL_DECL):
    def __init__(self, sig):
        self.sig = sig

    def __str__(self):
        return 'reg {}'.format(self.sig)

class AHDL_REG_ARRAY_DECL(AHDL_SIGNAL_DECL):
    def __init__(self, sig, size):
        self.sig = sig
        self.size = size

    def __str__(self):
        return 'reg {}[{}]'.format(self.sig, self.size)

class AHDL_NET_DECL(AHDL_SIGNAL_DECL):
    def __init__(self, sig):
        self.sig = sig

    def __str__(self):
        return 'net {}'.format(self.sig)

class AHDL_NET_ARRAY_DECL(AHDL_SIGNAL_DECL):
    def __init__(self, sig, size):
        self.sig = sig
        self.size = size

    def __str__(self):
        return 'net {}[{}]'.format(self.sig, self.size)

class AHDL_ASSIGN(AHDL_DECL):
    def __init__(self, dst, src):
        assert dst.is_a(AHDL)
        assert src.is_a(AHDL)
        super().__init__()
        self.dst = dst
        self.src = src

    def __str__(self):
        return '{} := {}'.format(self.dst, self.src)

class AHDL_CONNECT(AHDL_STM):
    def __init__(self, dst, src):
        assert dst.is_a(AHDL)
        assert src.is_a(AHDL)
        super().__init__()
        self.dst = dst
        self.src = src

    def __str__(self):
        return '{} = {}'.format(self.dst, self.src)

class AHDL_STORE(AHDL_STM):
    def __init__(self, mem, src, offset):
        assert isinstance(mem, AHDL_MEMVAR)
        assert mem.memnode.is_sink()
        super().__init__()
        self.mem = mem
        self.src = src
        self.offset = offset

    def __str__(self):
        return '{}[{}] <= {}'.format(self.mem, self.offset, self.src)

class AHDL_LOAD(AHDL_STM):
    def __init__(self, mem, dst, offset):
        assert isinstance(mem, AHDL_MEMVAR)
        assert mem.memnode.is_sink()
        super().__init__()
        self.mem = mem
        self.dst = dst
        self.offset = offset

    def __str__(self):
        return '{} <= {}[{}]'.format(self.dst, self.mem, self.offset)

class AHDL_FIELD_MOVE(AHDL_MOVE):
    def __init__(self, inst_name, attr_name, dst, src, is_ext):
        super().__init__(dst, src)
        self.inst_name = inst_name
        self.attr_name = attr_name
        self.is_ext = is_ext

    def __str__(self):
        return '{}.{} <= {}'.format(self.inst_name, self.dst, self.src)

class AHDL_FIELD_STORE(AHDL_STORE):
    def __init__(self, inst_name, mem, src, offset):
        super().__init__(mem, src, offset)
        self.inst_name = inst_name

    def __str__(self):
        return '{}[{}] <= {}'.format(self.mem, self.offset, self.src)

class AHDL_FIELD_LOAD(AHDL_LOAD):
    def __init__(self, inst_name, mem, dst, offset):
        super().__init__(mem, dst, offset)
        self.inst_name = inst_name

    def __str__(self):
        return '{} <= {}[{}]'.format(self.dst, self.mem, self.offset)

class AHDL_POST_PROCESS(AHDL_STM):
    def __init__(self, factor):
        super().__init__()
        self.factor = factor

    def __str__(self):
        return 'Post-process of : {}'.format(self.factor)

   

# ([cond], [code]) => if (cond) code
# ([cond, None], [code1, code2]) => if (cond) code1 else code2

class AHDL_IF(AHDL_STM):
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

class AHDL_IF_EXP(AHDL_EXP):
    def __init__(self, cond, lexp, rexp):
        super().__init__()
        self.cond = cond
        self.lexp = lexp
        self.rexp = rexp

    def __str__(self):
        return '{} ? {} : {}\n'.format(self.cond, self.lexp, self.rexp)

class AHDL_MODULECALL(AHDL_STM):
    def __init__(self, scope, args, instance_name, prefix):
        assert isinstance(instance_name, str)
        assert isinstance(prefix, str)
        super().__init__()
        self.scope = scope
        self.args = args
        self.instance_name = instance_name
        self.prefix = prefix

    def __str__(self):
        return '{}({})'.format(self.instance_name, ', '.join([str(arg) for arg in self.args]))

class AHDL_FUNCALL(AHDL_EXP):
    def __init__(self, name, args):
        assert isinstance(name, str)
        super().__init__()
        self.name = name
        self.args = args

    def __str__(self):
        return '{}({})'.format(self.name, ', '.join([str(arg) for arg in self.args]))

class AHDL_PROCCALL(AHDL_EXP):
    def __init__(self, name, args):
        assert isinstance(name, str)
        super().__init__()
        self.name = name
        self.args = args

    def __str__(self):
        return '{}({})'.format(self.name, ', '.join([str(arg) for arg in self.args]))

class AHDL_META(AHDL_STM):
    def __init__(self, *args):
        super().__init__()
        self.metaid = args[0]
        self.args = args[1:]

    def __str__(self):
        return '{}({})'.format(self.metaid, ', '.join([str(arg) for arg in self.args]))

class AHDL_META_WAIT(AHDL_STM):
    def __init__(self, *args):
        super().__init__()
        self.metaid = args[0]
        self.args = args[1:]
        self.transition = None

    def __str__(self):
        return '{}({})'.format(self.metaid, ', '.join([str(arg) for arg in self.args]))

class AHDL_FUNCTION(AHDL_DECL):
    def __init__(self, output, inputs, stms):
        super().__init__()
        self.inputs = inputs
        self.output = output
        self.stms = stms

    def __str__(self):
        return 'function {}'.format(self.name)


class AHDL_MUX(AHDL_DECL):
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


class AHDL_DEMUX(AHDL_DECL):
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


class AHDL_COMB(AHDL_DECL):
    def __init__(self, name, stms):
        super().__init__()
        assert isinstance(name, str)
        self.name = name
        self.stms = stms

    def __str__(self):
        return 'COMB {}'.format(self.name)


class AHDL_CASE(AHDL_STM):
    def __init__(self, sel, items):
        super().__init__()
        self.sel = sel
        self.items = items

    def __str__(self):
        return 'case' + ', '.join([str(item) for item in self.items])


class AHDL_CASE_ITEM(AHDL_STM):
    def __init__(self, val, stm):
        super().__init__()
        self.val = val
        self.stm = stm

    def __str__(self):
        return '{}:{}'.format(self.val, str(self.stm))


class AHDL_TRANSITION(AHDL_STM):
    def __init__(self, target):
        self.target = target

    def __str__(self):
        return '(next state: {})'.format(self.target.name)

class AHDL_TRANSITION_IF(AHDL_IF):
    def __init__(self, conds, codes_list):
        super().__init__(conds, codes_list)
