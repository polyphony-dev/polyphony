from .signal import Signal
from .ir import Ctx
from .memref import MemRefNode, MemParamNode
from .utils import is_a

PYTHON_OP_2_HDL_OP_MAP = {
    'And': '&&', 'Or': '||',
    'Add': '+', 'Sub': '-', 'Mult': '*', 'FloorDiv': '//', 'Mod': '%',
    'LShift': '<<', 'RShift': '>>',
    'BitOr': '|', 'BitXor': '^', 'BitAnd': '&',
    'Eq': '==', 'NotEq': '!=', 'Lt': '<', 'LtE': '<=', 'Gt': '>', 'GtE': '>=',
    'IsNot': '!=',
    'USub': '-', 'UAdd': '+', 'Not': '!', 'Invert': '~'
}


class AHDL(object):
    '''Abstract HDL'''
    def __init__(self):
        pass

    def is_a(self, cls):
        return is_a(self, cls)


class AHDL_EXP(AHDL):
    pass


class AHDL_CONST(AHDL_EXP):
    def __init__(self, value):
        super().__init__()
        self.value = value

    def __str__(self):
        return '{}'.format(self.value)

    def __repr__(self):
        return 'AHDL_CONST({})'.format(repr(self.value))


class AHDL_OP(AHDL_EXP):
    def __init__(self, op, *args):
        super().__init__()
        self.op = op
        self.args = args

    def __str__(self):
        if len(self.args) > 1:
            op = ' ' + PYTHON_OP_2_HDL_OP_MAP[self.op] + ' '
            str_args = [str(a) for a in self.args]
            return '({})'.format(op.join(str_args))
        else:
            return '({}{})'.format(PYTHON_OP_2_HDL_OP_MAP[self.op], self.args[0])

    def __repr__(self):
        args = ', '.join([repr(arg) for arg in self.args])
        return 'AHDL_OP({}, {})'.format(repr(self.op), args)

    def is_relop(self):
        return self.op in ('And', 'Or', 'Eq', 'NotEq', 'Lt', 'LtE', 'Gt', 'GtE')


class AHDL_VAR(AHDL_EXP):
    def __init__(self, sig, ctx):
        assert sig and isinstance(sig, Signal)
        super().__init__()
        self.sig = sig
        self.ctx = ctx

    def __str__(self):
        return '{}'.format(self.sig)

    def __repr__(self):
        return 'AHDL_VAR({}, {})'.format(repr(self.sig), repr(self.ctx))


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

    def __repr__(self):
        return 'AHDL_MEMVAR({}, {}, {})'.format(repr(self.sig),
                                                repr(self.memnode),
                                                repr(self.ctx))

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

    def __repr__(self):
        return 'AHDL_SUBSCRIPT({}, {})'.format(repr(self.memvar), repr(self.offset))


class AHDL_SYMBOL(AHDL_EXP):
    def __init__(self, name):
        assert name and isinstance(name, str)
        super().__init__()
        self.name = name

    def __str__(self):
        return '{}'.format(self.name)

    def __repr__(self):
        return 'AHDL_SYMBOL({})'.format(repr(self.name))


class AHDL_CONCAT(AHDL_EXP):
    def __init__(self, varlist, op=None):
        super().__init__()
        assert isinstance(varlist, list)
        self.varlist = varlist
        self.op = op

    def __str__(self):
        if self.op:
            op = PYTHON_OP_2_HDL_OP_MAP[self.op]
            return '{{{0}}}'.format(op.join([str(v) for v in self.varlist]))
        else:
            return '{{{0}}}'.format(', '.join([str(v) for v in self.varlist]))

    def __repr__(self):
        return 'AHDL_CONCAT({}, {})'.format(repr(self.varlist), repr(self.op))


class AHDL_STM(AHDL):
    pass


class AHDL_NOP(AHDL_STM):
    def __init__(self, info):
        super().__init__()
        self.info = info

    def __str__(self):
        return 'nop for {}'.format(self.info)

    def __repr__(self):
        return 'AHDL_NOP({})'.format(repr(self.info))


class AHDL_INLINE(AHDL_STM):
    def __init__(self, code):
        super().__init__()
        assert isinstance(code, str)
        self.code = code

    def __str__(self):
        return '{}'.format(self.code)

    def __repr__(self):
        return 'AHDL_INLINE({})'.format(repr(self.code))


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

    def __repr__(self):
        return 'AHDL_MOVE({}, {})'.format(repr(self.dst), repr(self.src))


class AHDL_DECL(AHDL):
    def __init__(self, name):
        assert isinstance(name, str)
        self.name = name


class AHDL_SIGNAL_DECL(AHDL_DECL):
    def __init__(self, sig):
        super().__init__(sig.name)
        self.sig = sig

    def __str__(self):
        sign = 'signed' if self.sig.is_int() else ''
        type = 'reg' if self.sig.is_reg() else 'net'
        return '{} {} {}'.format(sign, type, self.sig)

    def __repr__(self):
        return 'AHDL_SIGNAL_DECL({})'.format(repr(self.sig))


class AHDL_SIGNAL_ARRAY_DECL(AHDL_SIGNAL_DECL):
    def __init__(self, sig, size):
        super().__init__(sig)
        self.name += '[{}]'.format(size)
        self.size = size

    def __str__(self):
        return '{}[{}]'.format(super().__str__(), self.size)

    def __repr__(self):
        return 'AHDL_SIGNAL_ARRAY_DECL({}, {})'.format(repr(self.sig), repr(self.size))


class AHDL_ASSIGN(AHDL_DECL):
    def __init__(self, dst, src):
        assert dst.is_a(AHDL)
        assert src.is_a(AHDL)
        if dst.is_a(AHDL_VAR):
            super().__init__(dst.sig.name)
        elif dst.is_a(AHDL_SUBSCRIPT):
            super().__init__(dst.memvar.sig.name + '[{}]'.format(dst.offset))
        else:
            assert False
        self.dst = dst
        self.src = src

    def __str__(self):
        return '{} := {}'.format(self.dst, self.src)

    def __repr__(self):
        return 'AHDL_ASSIGN({}, {})'.format(repr(self.dst), repr(self.src))


class AHDL_CONNECT(AHDL_STM):
    def __init__(self, dst, src):
        assert dst.is_a(AHDL)
        assert src.is_a(AHDL)
        super().__init__()
        self.dst = dst
        self.src = src

    def __str__(self):
        return '{} = {}'.format(self.dst, self.src)

    def __repr__(self):
        return 'AHDL_CONNECT({}, {})'.format(repr(self.dst), repr(self.src))


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

    def __repr__(self):
        return 'AHDL_STORE({}, {}, {})'.format(repr(self.mem),
                                               repr(self.src),
                                               repr(self.offset))


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

    def __repr__(self):
        return 'AHDL_LOAD({}, {}, {})'.format(repr(self.mem),
                                              repr(self.dst),
                                              repr(self.offset))


class AHDL_IO_READ(AHDL_STM):
    def __init__(self, io, dst, is_self=True):
        super().__init__()
        self.io = io
        self.dst = dst
        self.is_self = is_self

    def __str__(self):
        return 'dst <= {}.read()'.format(self.dst, self.io)

    def __repr__(self):
        return 'AHDL_IO_READ({}, {})'.format(repr(self.io),
                                             repr(self.dst))


class AHDL_IO_WRITE(AHDL_STM):
    def __init__(self, io, src, is_self=True):
        super().__init__()
        self.io = io
        self.src = src
        self.is_self = is_self

    def __str__(self):
        return '{}.write({})'.format(self.io, self.src)

    def __repr__(self):
        return 'AHDL_IO_WRITE({}, {})'.format(repr(self.io),
                                              repr(self.src))


class AHDL_SEQ(AHDL_STM):
    def __init__(self, factor, step, step_n):
        super().__init__()
        self.factor = factor
        self.step = step
        self.step_n = step_n

    def __str__(self):
        return 'Sequence {} : {}'.format(self.step, self.factor)

    def __repr__(self):
        return 'AHDL_SEQ({}, {})'.format(repr(self.factor), repr(self.step))


class AHDL_IF(AHDL_STM):
    # ([cond], [code]) => if (cond) code
    # ([cond, None], [code1, code2]) => if (cond) code1 else code2
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

    def __repr__(self):
        return 'AHDL_IF({}, {})'.format(repr(self.conds), repr(self.codes_list))


class AHDL_IF_EXP(AHDL_EXP):
    def __init__(self, cond, lexp, rexp):
        super().__init__()
        self.cond = cond
        self.lexp = lexp
        self.rexp = rexp

    def __str__(self):
        return '{} ? {} : {}'.format(self.cond, self.lexp, self.rexp)

    def __repr__(self):
        return 'AHDL_IF_EXP({}, {}, {})'.format(repr(self.cond),
                                                repr(self.lexp),
                                                repr(self.rexp))


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

    def __repr__(self):
        return 'AHDL_MODULECALL({}, {}, {}, {})'.format(repr(self.scope),
                                                        repr(self.args),
                                                        repr(self.instance_name),
                                                        repr(self.prefix))


class AHDL_CALLEE_PROLOG(AHDL_STM):
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return 'AHDL_CALLEE_PROLOG({})'.format(repr(self.name))


class AHDL_CALLEE_EPILOG(AHDL_STM):
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return 'AHDL_CALLEE_EPILOG({})'.format(repr(self.name))


class AHDL_FUNCALL(AHDL_EXP):
    def __init__(self, name, args):
        assert isinstance(name, AHDL_SYMBOL)
        super().__init__()
        self.name = name
        self.args = args

    def __str__(self):
        return '{}({})'.format(self.name, ', '.join([str(arg) for arg in self.args]))

    def __repr__(self):
        return 'AHDL_FUNCALL({}, {})'.format(repr(self.name), repr(self.args))


class AHDL_PROCCALL(AHDL_STM):
    def __init__(self, name, args):
        assert isinstance(name, str)
        super().__init__()
        self.name = name
        self.args = args

    def __str__(self):
        return '{}({})'.format(self.name, ', '.join([str(arg) for arg in self.args]))

    def __repr__(self):
        return 'AHDL_PROCCALL({}, {})'.format(repr(self.name), repr(self.args))


class AHDL_META(AHDL_STM):
    def __init__(self, *args):
        super().__init__()
        self.metaid = args[0]
        self.args = args[1:]

    def __str__(self):
        return '{}({})'.format(self.metaid, ', '.join([str(arg) for arg in self.args]))

    def __repr__(self):
        args = [repr(self.metaid)] + [repr(a) for a in self.args]
        return 'AHDL_META({})'.format(', '.join(args))


class AHDL_META_WAIT(AHDL_STM):
    def __init__(self, *args):
        super().__init__()
        self.metaid = args[0]
        self.args = args[1:]
        self.codes = None
        self.transition = None

    def __str__(self):
        s = '{}({})'.format(self.metaid, ', '.join([str(arg) for arg in self.args]))
        if self.codes:
            s += '\n'
            s += '\n'.join(['  {}'.format(code) for code in self.codes])
        elif self.transition:
            s += '\n'
            s += '  {}'.format(self.transition)
        return s

    def __repr__(self):
        args = [repr(self.metaid)] + [repr(a) for a in self.args]
        return 'AHDL_META_WAIT({})'.format(', '.join(args))


class AHDL_FUNCTION(AHDL_DECL):
    def __init__(self, output, inputs, stms):
        assert isinstance(output, AHDL_VAR)
        super().__init__(output.sig.name)
        self.inputs = inputs
        self.output = output
        self.stms = stms

    def __str__(self):
        return 'function {}'.format(self.output)

    def __repr__(self):
        return 'AHDL_FUNCTION({}, {}, {})'.format(
            repr(self.output),
            repr(self.inputs),
            repr(self.stms)
        )


class AHDL_MUX(AHDL_DECL):
    def __init__(self, name, selector, inputs, output):
        super().__init__(name)
        assert isinstance(output, Signal)
        self.selector = selector
        self.inputs = inputs
        self.output = output

    def __str__(self):
        return 'MUX {}'.format(self.name)


class AHDL_DEMUX(AHDL_DECL):
    def __init__(self, name, selector, input, outputs):
        super().__init__(name)
        assert isinstance(input, Signal)
        self.selector = selector
        self.input = input
        self.outputs = outputs

    def __str__(self):
        return 'DEMUX {}'.format(self.name)


class AHDL_COMB(AHDL_DECL):
    def __init__(self, name, stms):
        super().__init__(name)
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

    def __repr__(self):
        return 'AHDL_TRANSITION({})'.format(self.target.name)


class AHDL_TRANSITION_IF(AHDL_IF):
    def __init__(self, conds, codes_list):
        super().__init__(conds, codes_list)

    def __repr__(self):
        return 'AHDL_TRANSITION_IF({}, {})'.format(repr(self.conds), repr(self.codes_list))
