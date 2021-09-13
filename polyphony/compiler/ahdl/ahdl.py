from .signal import Signal
from ..ir.ir import Ctx
from ..common.utils import is_a

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

    def find_ahdls(self, typ):
        ahdls = []

        def find_ahdls_rec(ahdl, typ, ahdls):
            #print(ahdl)
            if ahdl.is_a(typ):
                ahdls.append(ahdl)
            for k, v in ahdl.__dict__.items():
                if isinstance(v, AHDL):
                    if v is self:
                        continue
                    find_ahdls_rec(v, typ, ahdls)
                elif isinstance(v, list) or isinstance(v, tuple):
                    for elm in filter(lambda w:isinstance(w, AHDL),  v):
                        find_ahdls_rec(elm, typ, ahdls)
        find_ahdls_rec(self, typ, ahdls)
        return ahdls


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

    def is_unop(self):
        return self.op in ('USub', 'UAdd', 'Not', 'Invert')


class AHDL_META_OP(AHDL_EXP):
    def __init__(self, op, *args):
        super().__init__()
        self.op = op
        self.args = args

    def __str__(self):
        str_args = [str(a) for a in self.args]
        return '({} {})'.format(self.op, ', '.join(str_args))

    def __repr__(self):
        args = ', '.join([repr(arg) for arg in self.args])
        return 'AHDL_META_OP({}, {})'.format(repr(self.op), args)


class AHDL_VAR(AHDL_EXP):
    def __init__(self, sig, ctx):
        assert sig and isinstance(sig, Signal)
        super().__init__()
        self.sig = sig
        self.ctx = ctx

    def __str__(self):
        return '{}'.format(self.sig.name)

    def __repr__(self):
        return 'AHDL_VAR(\'{}\')'.format(self.sig)


class AHDL_MEMVAR(AHDL_VAR):
    def __init__(self, sig, ctx):
        super().__init__(sig, ctx)

    def __str__(self):
        return '{}[]'.format(self.sig.name)

    def __repr__(self):
        return 'AHDL_MEMVAR(\'{}\')'.format(self.sig)

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


class AHDL_SLICE(AHDL_EXP):
    def __init__(self, var, hi, lo):
        super().__init__()
        self.var = var
        self.hi = hi
        self.lo = lo

    def __str__(self):
        return '{}[{}:{}]'.format(self.var, self.hi, self.lo)

    def __repr__(self):
        return 'AHDL_SLICE({}, {}, {})'.format(repr(self.var), repr(self.hi), repr(self.lo))


class AHDL_STM(AHDL):
    def __init__(self):
        self.guard_cond = None


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
        if self.dst.is_a(AHDL_VAR) and self.dst.sig.is_net():
            return '{} := {}'.format(self.dst, self.src)
        return '{} <= {}'.format(self.dst, self.src)

    def __repr__(self):
        return 'AHDL_MOVE({}, {})'.format(repr(self.dst), repr(self.src))


class AHDL_DECL(AHDL_STM):
    pass


class AHDL_VAR_DECL(AHDL_DECL):
    def __init__(self, name):
        assert isinstance(name, str)
        self.name = name


class AHDL_ASSIGN(AHDL_VAR_DECL):
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


class AHDL_EVENT_TASK(AHDL_DECL):
    def __init__(self, events, stm):
        assert isinstance(events, list)
        assert isinstance(stm, AHDL_STM)
        self.events = events
        self.stm = stm

    def __str__(self):
        events = ', '.join('{} {}'.format(ev, var) for var, ev in self.events)
        return '({})\n{}'.format(events, self.stm)

    def __repr__(self):
        return 'AHDL_EVENT_TASK({}, {})'.format(repr(self.events), repr(self.stm))


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


class AHDL_IO_READ(AHDL_STM):
    def __init__(self, io, dst, is_self=True):
        super().__init__()
        self.io = io
        self.dst = dst
        self.is_self = is_self

    def __str__(self):
        return '{} <= {}.rd()'.format(self.dst, self.io)

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
        return '{}.wr({})'.format(self.io, self.src)

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
    def __init__(self, conds, blocks):
        super().__init__()
        self.conds = conds
        self.blocks = blocks
        assert len(conds) == len(blocks)
        assert conds[0]

    def __str__(self):
        s = 'if {}\n'.format(self.conds[0])
        for code in self.blocks[0].codes:
            str_code = str(code)
            lines = str_code.split('\n')
            for line in lines:
                s += '  {}\n'.format(line)
        for cond, ahdlblk in zip(self.conds[1:], self.blocks[1:]):
            if cond:
                s += 'elif {}\n'.format(cond)
                for code in ahdlblk.codes:
                    str_code = str(code)
                    lines = str_code.split('\n')
                    for line in lines:
                        s += '  {}\n'.format(line)
            else:
                s += 'else\n'
                for code in ahdlblk.codes:
                    str_code = str(code)
                    lines = str_code.split('\n')
                    for line in lines:
                        s += '  {}\n'.format(line)
        return s

    def __repr__(self):
        return 'AHDL_IF({}, {})'.format(repr(self.conds), repr(self.blocks))


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
        self.returns = []

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
        self.args = list(args[1:])

    def __str__(self):
        return '{}({})'.format(self.metaid, ', '.join([str(arg) for arg in self.args]))

    def __repr__(self):
        args = [repr(self.metaid)] + [repr(a) for a in self.args]
        return 'AHDL_META({})'.format(', '.join(args))


class AHDL_META_WAIT(AHDL_STM):
    def __init__(self, *args, waiting_stms=None):
        super().__init__()
        self.metaid = args[0]
        self.args = list(args[1:])
        self.waiting_stms = waiting_stms

    def __str__(self):
        items = []
        for arg in self.args:
            if isinstance(arg, (list, tuple)):
                items.append(', '.join([str(a) for a in arg]))
            else:
                items.append(str(arg))
        s = '{}({})'.format(self.metaid, ', '.join(items))
        return s

    def __repr__(self):
        args = [repr(self.metaid)] + [repr(a) for a in self.args]
        return 'AHDL_META_WAIT({})'.format(', '.join(args))


class AHDL_FUNCTION(AHDL_VAR_DECL):
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


class AHDL_COMB(AHDL_VAR_DECL):
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
        return f'case {self.sel}\n' + '\n'.join([str(item) for item in self.items])

    def __repr__(self):
        return 'AHDL_CASE({})'.format(repr(self.sel))


class AHDL_CASE_ITEM(AHDL_STM):
    def __init__(self, val, block):
        super().__init__()
        self.val = val
        self.block = block

    def __str__(self):
        return '{}:{}'.format(self.val, str(self.block))

    def __repr__(self):
        return 'AHDL_CASE_ITEM({})'.format(repr(self.val))


class AHDL_TRANSITION(AHDL_STM):
    def __init__(self, target):
        self.target = target

    def __str__(self):
        return '(next state: {})'.format(self.target.name)

    def __repr__(self):
        return 'AHDL_TRANSITION({})'.format(self.target.name)


class AHDL_TRANSITION_IF(AHDL_IF):
    def __init__(self, conds, blocks):
        super().__init__(conds, blocks)

    def __repr__(self):
        return 'AHDL_TRANSITION_IF({}, {})'.format(repr(self.conds), repr(self.blocks))


class AHDL_PIPELINE_GUARD(AHDL_IF):
    def __init__(self, cond, codes):
        super().__init__([cond], [AHDL_BLOCK('', codes)])

    def __repr__(self):
        return 'AHDL_PIPELINE_GUARD({}, {})'.format(repr(self.conds), repr(self.blocks))


class AHDL_BLOCK(AHDL):
    def __init__(self, name, codes):
        self.name = name
        self.codes = codes

    def __str__(self):
        return 'begin\n' + ('\n'.join([str(c) for c in self.codes])) + '\nend'

    def __repr__(self):
        return 'AHDL_BLOCK({})'.format(', '.join([repr(c) for c in self.codes]))

    def traverse(self):
        codes = []
        for c in self.codes:
            if c.is_a(AHDL_BLOCK):
                codes.extend(c.traverse())
            else:
                codes.append(c)
        return codes
