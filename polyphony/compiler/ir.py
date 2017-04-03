from enum import IntEnum
from .utils import is_a
from .symbol import Symbol

op2sym_map = {
    'And': 'and', 'Or': 'or',
    'Add': '+', 'Sub': '-', 'Mult': '*', 'FloorDiv': '//', 'Mod': '%',
    'LShift': '<<', 'RShift': '>>',
    'BitOr': '|', 'BitXor': '^', 'BitAnd': '&',
    'Eq': '==', 'NotEq': '!=', 'Lt': '<', 'LtE': '<=', 'Gt': '>', 'GtE': '>=',
    'IsNot': '!=',
    'USub': '-', 'UAdd': '+', 'Not': '!', 'Invert': '~'
}


class Ctx(IntEnum):
    LOAD = 1
    STORE = 2


class IR(object):
    def __init__(self):
        self.lineno = -1

    def __repr__(self):
        return self.__str__()

    def __hash__(self):
        return super().__hash__()

    def __lt__(self, other):
        return hash(self) < hash(other)

    def is_a(self, cls):
        return is_a(self, cls)

    def clone(self):
        clone = self.__new__(self.__class__)
        clone.__dict__ = self.__dict__.copy()
        for k, v in clone.__dict__.items():
            if isinstance(v, IR):
                clone.__dict__[k] = v.clone()
            elif isinstance(v, list):
                li = []
                for elm in v:
                    if isinstance(elm, IR):
                        li.append(elm.clone())
                    else:
                        li.append(elm)
                clone.__dict__[k] = li
        return clone

    def replace(self, old, new):
        def replace_rec(ir, old, new):
            if isinstance(ir, IR):
                if ir.is_a([CALL, SYSCALL, NEW]):
                    return ir.replace(old, new)
                for k, v in ir.__dict__.items():
                    if v is old:
                        ir.__dict__[k] = new
                        return True
                    elif replace_rec(v, old, new):
                        return True
            elif isinstance(ir, list):
                for i, elm in enumerate(ir):
                    if elm is old:
                        ir[i] = new
                        return True
                    elif replace_rec(elm, old, new):
                        return True
            return False
        return replace_rec(self, old, new)

    def find_vars(self, qsym):
        vars = []

        def find_vars_rec(ir, qsym, vars):
            if isinstance(ir, IR):
                if ir.is_a([CALL, SYSCALL, NEW]):
                    vars.extend(ir.find_vars(qsym))
                elif ir.is_a(TEMP):
                    if ir.qualified_symbol() == qsym:
                        vars.append(ir)
                elif ir.is_a(ATTR):
                    if ir.qualified_symbol() == qsym:
                        vars.append(ir)
                    else:
                        find_vars_rec(ir.exp, qsym, vars)
                else:
                    for k, v in ir.__dict__.items():
                        find_vars_rec(v, qsym, vars)
            elif isinstance(ir, list) or isinstance(ir, tuple):
                for elm in ir:
                    find_vars_rec(elm, qsym, vars)
        find_vars_rec(self, qsym, vars)
        return vars

    def find_irs(self, typ):
        irs = []

        def find_irs_rec(ir, typ, irs):
            if isinstance(ir, IR):
                if ir.is_a(typ):
                    irs.append(ir)
                if ir.is_a([CALL, SYSCALL, NEW]):
                    irs.extend(ir.find_irs(typ))
                    return
                for k, v in ir.__dict__.items():
                    find_irs_rec(v, typ, irs)
            elif isinstance(ir, list) or isinstance(ir, tuple):
                for elm in ir:
                    find_irs_rec(elm, typ, irs)
        find_irs_rec(self, typ, irs)
        return irs


class IRExp(IR):
    def __init__(self):
        super().__init__()


class UNOP(IRExp):
    def __init__(self, op, exp):
        super().__init__()
        self.op = op
        self.exp = exp
        assert op in {'USub', 'UAdd', 'Not', 'Invert'}

    def __str__(self):
        return '{}{}'.format(op2sym_map[self.op], self.exp)

    def __eq__(self, other):
        if other is None or not other.is_a(UNOP):
            return False
        return self.op == other.op and self.exp == other.exp

    def __hash__(self):
        return super().__hash__()

    def kids(self):
        return self.exp.kids()


class BINOP(IRExp):
    def __init__(self, op, left, right):
        super().__init__()
        self.op = op
        self.left = left
        self.right = right
        assert op in {
            'Add', 'Sub', 'Mult', 'FloorDiv', 'Mod',
            'LShift', 'RShift',
            'BitOr', 'BitXor', 'BitAnd',
        }

    def __str__(self):
        return '({} {} {})'.format(self.left, op2sym_map[self.op], self.right)

    def __eq__(self, other):
        if other is None or not other.is_a(BINOP):
            return False
        return (self.op == other.op and self.left == other.left and self.right == other.right)

    def __hash__(self):
        return super().__hash__()

    def kids(self):
        return self.left.kids() + self.right.kids()


class RELOP(IRExp):
    def __init__(self, op, left, right):
        super().__init__()
        self.op = op
        self.left = left
        self.right = right
        assert op in {
            'And', 'Or',
            'Eq', 'NotEq', 'Lt', 'LtE', 'Gt', 'GtE',
            'IsNot',
        }

    def __str__(self):
        return '({} {} {})'.format(self.left, op2sym_map[self.op], self.right)

    def __eq__(self, other):
        if other is None or not other.is_a(RELOP):
            return False
        return (self.op == other.op and self.left == other.left and self.right == other.right)

    def __hash__(self):
        return super().__hash__()

    def kids(self):
        return self.left.kids() + self.right.kids()


class CONDOP(IRExp):
    def __init__(self, cond, left, right):
        super().__init__()
        self.cond = cond
        self.left = left
        self.right = right

    def __str__(self):
        return '({} ? {} : {})'.format(self.cond, self.left, self.right)

    def __eq__(self, other):
        if other is None or not other.is_a(CONDOP):
            return False
        return (self.cond == other.cond and self.left == other.left and self.right == other.right)

    def __hash__(self):
        return super().__hash__()

    def kids(self):
        return self.cond.kids() + self.left.kids() + self.right.kids()


def replace_args(args, old, new):
    for i, (name, arg) in enumerate(args):
        if arg is old:
            args[i] = (name, new)
            return True
        if arg.replace(old, new):
            return True
    return False


def find_vars_args(args, qsym):
    vars = []
    for _, arg in args:
        if arg.is_a([TEMP, ATTR]) and arg.qualified_symbol() == qsym:
            vars.append(arg)
        vars.extend(arg.find_vars(qsym))
    return vars


def find_irs_args(args, typ):
    irs = []
    for _, arg in args:
        if arg.is_a(typ):
            irs.append(arg)
        irs.extend(arg.find_irs(typ))
    return irs


class CALL(IRExp):
    def __init__(self, func, args, kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.func_scope = None

    def __str__(self):
        s = '(CALL {}, '.format(self.func)
        s += ', '.join(['{}={}'.format(name, arg) for name, arg in self.args])
        s += ")"
        return s

    def __eq__(self, other):
        if other is None or not other.is_a(CALL):
            return False
        return (self.func == other.func and
                len(self.args) == len(other.args) and
                all([name == other_name and a == other_a
                     for (name, a), (other_name, other_a) in zip(self.args, other.args)]))

    def __hash__(self):
        return super().__hash__()

    def kids(self):
        kids = []
        kids += self.func.kids()
        for _, arg in self.args:
            kids += arg.kids()
        return kids

    def clone(self):
        func = self.func.clone()
        args = [(name, arg.clone()) for name, arg in self.args]
        clone = CALL(func, args, {})
        clone.func_scope = self.func_scope
        clone.lineno = self.lineno
        return clone

    def replace(self, old, new):
        if self.func is old:
            self.func = new
            return True
        if self.func.replace(old, new):
            return True
        if replace_args(self.args, old, new):
            return True
        return False

    def find_vars(self, qsym):
        vars = self.func.find_vars(qsym)
        vars.extend(find_vars_args(self.args, qsym))
        return vars

    def find_irs(self, typ):
        irs = self.func.find_irs(typ)
        irs.extend(find_irs_args(self.args, typ))
        return irs


class SYSCALL(IRExp):
    def __init__(self, sym, args, kwargs):
        super().__init__()
        assert isinstance(sym, Symbol)
        self.sym = sym
        self.args = args
        self.kwargs = kwargs

    def __str__(self):
        s = '(SYSCALL {}, '.format(self.sym)
        s += ', '.join(['{}={}'.format(name, arg) for name, arg in self.args])
        s += ")"
        return s

    def __eq__(self, other):
        if other is None or not other.is_a(SYSCALL):
            return False
        return (self.sym is other.sym and
                len(self.args) == len(other.args) and
                all([name == other_name and a == other_a
                     for (name, a), (other_name, other_a) in zip(self.args, other.args)]))

    def __hash__(self):
        return super().__hash__()

    def kids(self):
        kids = []
        for _, arg in self.args:
            kids += arg.kids()
        return kids

    def clone(self):
        args = [(name, arg.clone()) for name, arg in self.args]
        clone = SYSCALL(self.sym, args, {})
        clone.lineno = self.lineno
        return clone

    def replace(self, old, new):
        return replace_args(self.args, old, new)

    def find_vars(self, qsym):
        return find_vars_args(self.args, qsym)

    def find_irs(self, typ):
        return find_irs_args(self.args, typ)


class NEW(IRExp):
    def __init__(self, scope, args, kwargs):
        super().__init__()
        self.func_scope = scope
        self.args = args
        self.kwargs = kwargs

    def __str__(self):
        s = '(NEW {}, '.format(self.func_scope.orig_name)
        s += ', '.join(['{}={}'.format(name, arg) for name, arg in self.args])
        s += ")"
        return s

    def __eq__(self, other):
        if other is None or not other.is_a(NEW):
            return False
        return (self.func_scope is other.func_scope and
                len(self.args) == len(other.args) and
                all([name == other_name and a == other_a
                     for (name, a), (other_name, other_a) in zip(self.args, other.args)]))

    def __hash__(self):
        return super().__hash__()

    def kids(self):
        kids = []
        for _, arg in self.args:
            kids += arg.kids()
        return kids

    def clone(self):
        args = [(name, arg.clone()) for name, arg in self.args]
        clone = NEW(self.func_scope, args, {})
        clone.lineno = self.lineno
        return clone

    def replace(self, old, new):
        return replace_args(self.args, old, new)

    def find_vars(self, qsym):
        return find_vars_args(self.args, qsym)

    def find_irs(self, typ):
        return find_irs_args(self.args, typ)


class CONST(IRExp):
    def __init__(self, value):
        super().__init__()
        self.value = value

    def __str__(self):
        if isinstance(self.value, bool):
            return str(self.value)
        elif isinstance(self.value, int):
            return hex(self.value)
        else:
            return repr(self.value)

    def __eq__(self, other):
        if other is None or not other.is_a(CONST):
            return False
        return self.value == other.value

    def __hash__(self):
        return super().__hash__()

    def kids(self):
        return [self]


class MREF(IRExp):
    def __init__(self, mem, offset, ctx):
        super().__init__()
        assert mem.is_a([TEMP, ATTR])
        self.mem = mem
        self.offset = offset
        self.ctx = ctx

    def __str__(self):
        return '(MREF {}, {})'.format(self.mem, self.offset)

    def __eq__(self, other):
        if other is None or not other.is_a(MREF):
            return False
        return (self.mem == other.mem and self.offset == other.offset and self.ctx == other.ctx)

    def __hash__(self):
        return super().__hash__()

    def kids(self):
        return self.mem.kids() + self.offset.kids()


class MSTORE(IRExp):
    def __init__(self, mem, offset, exp):
        super().__init__()
        self.mem = mem
        self.offset = offset
        self.exp = exp

    def __str__(self):
        return '(MSTORE {}, {}, {})'.format(self.mem, self.offset, self.exp)

    def __eq__(self, other):
        if other is None or not other.is_a(MSTORE):
            return False
        return (self.mem == other.mem and self.offset == other.offset and self.exp == other.exp)

    def __hash__(self):
        return super().__hash__()

    def kids(self):
        return self.mem.kids() + self.offset.kids() + self.exp.kids()


class ARRAY(IRExp):
    def __init__(self, items, is_mutable=True):
        super().__init__()
        self.items = items
        self.sym = None
        self.repeat = CONST(1)
        self.is_mutable = is_mutable

    def __str__(self):
        s = "(ARRAY "
        s += '[' if self.is_mutable else '('
        if len(self.items) > 8:
            s += ', '.join(map(str, self.items[:10]))
            s += '...'
        else:
            s += ', '.join(map(str, self.items))
        s += ']' if self.is_mutable else ')'
        if not (self.repeat.is_a(CONST) and self.repeat.value == 1):
            s += ' * ' + str(self.repeat)
        s += ")"
        return s

    def __eq__(self, other):
        if other is None or not other.is_a(ARRAY):
            return False
        return (len(self.items) == len(other.items) and
                all([item == other_item for item, other_item in zip(self.items, other.items)]) and
                self.sym is other.sym and
                self.repeat == other.repeat and
                self.is_mutable == other.is_mutable)

    def __hash__(self):
        return super().__hash__()

    def kids(self):
        kids = []
        for item in self.items:
            kids += item.kids()
        return kids

    def getlen(self):
        if self.repeat.is_a(CONST):
            return len(self.items) * self.repeat.value
        else:
            return -1


class TEMP(IRExp):
    def __init__(self, sym, ctx):
        super().__init__()
        self.sym = sym
        self.ctx = ctx
        assert isinstance(ctx, int)

    def __str__(self):
        return str(self.sym)

    def __eq__(self, other):
        if other is None or not other.is_a(TEMP):
            return False
        return (self.sym is other.sym and self.ctx == other.ctx)

    def __hash__(self):
        return super().__hash__()

    def kids(self):
        return [self]

    def symbol(self):
        return self.sym

    def set_symbol(self, sym):
        self.sym = sym

    def qualified_symbol(self):
        return (self.sym, )


class ATTR(IRExp):
    def __init__(self, exp, attr, ctx, attr_scope=None):
        super().__init__()
        self.exp = exp
        self.attr = attr
        self.ctx = ctx
        self.attr_scope = attr_scope
        self.exp.ctx = Ctx.LOAD

    def __str__(self):
        return '{}.{}'.format(self.exp, self.attr)

    def __eq__(self, other):
        if other is None or not other.is_a(ATTR):
            return False
        return (self.exp == other.exp and
                self.attr is other.attr and
                self.ctx == other.ctx and
                self.attr_scope is other.attr_scope)

    def __hash__(self):
        return super().__hash__()

    def kids(self):
        return [self]

    # a.b.c.d = (((a.b).c).d)
    #              |    |
    #             head  |
    #                  tail
    def head(self):
        if self.exp.is_a(ATTR):
            return self.exp.head()
        elif self.exp.is_a(TEMP):
            return self.exp.sym
        else:
            return None

    def tail(self):
        if self.exp.is_a(ATTR):
            #assert isinstance(self.exp.attr, Symbol)
            return self.exp.attr
        return self.exp.sym

    def symbol(self):
        return self.attr

    def set_symbol(self, sym):
        self.attr = sym

    def qualified_symbol(self):
        return self.exp.qualified_symbol() + (self.attr,)


class IRStm(IR):
    def __init__(self):
        super().__init__()
        self.block = None

    def program_order(self):
        return (self.block.order, self.block.stms.index(self))

    def kids(self):
        return []


class EXPR(IRStm):
    def __init__(self, exp):
        super().__init__()
        self.exp = exp

    def __str__(self):
        return '(EXPR {})'.format(self.exp)

    def __eq__(self, other):
        if other is None or not other.is_a(EXPR):
            return False
        return self.exp == other.exp

    def __hash__(self):
        return super().__hash__()

    def kids(self):
        return self.exp.kids()


class CJUMP(IRStm):
    def __init__(self, exp, true, false):
        super().__init__()
        self.exp = exp
        self.true = true
        self.false = false
        self.loop_branch = False

    def __str__(self):
        return '(CJUMP {}, {}, {})'.format(self.exp, self.true.name, self.false.name)

    def __eq__(self, other):
        if other is None or not other.is_a(CJUMP):
            return False
        return self.exp == other.exp and self.true is other.true and self.false is other.false

    def __hash__(self):
        return super().__hash__()


class MCJUMP(IRStm):
    def __init__(self):
        super().__init__()
        self.conds = []
        self.targets = []
        self.loop_branch = False

    def __str__(self):
        assert len(self.conds) == len(self.targets)
        items = []
        for cond, target in zip(self.conds, self.targets):
            items.append('({}) => {}'.format(cond, target.name))

        return '(MCJUMP \n        {})'.format(', \n        '.join([item for item in items]))

    def __eq__(self, other):
        if other is None or not other.is_a(MCJUMP):
            return False
        return (len(self.conds) == len(other.conds) and
                all([cond == other_cond for cond, other_cond in zip(self.conds, other.conds)]) and
                all([target is other_target for target, other_target in zip(self.targets, other.targets)]))

    def __hash__(self):
        return super().__hash__()


class JUMP(IRStm):
    def __init__(self, target, typ=''):
        super().__init__()
        self.target = target
        self.typ = typ  # 'B': break, 'C': continue, 'L': loop-back, 'S': specific

    def __str__(self):
        return "(JUMP {} '{}')".format(self.target.name, self.typ)

    def __eq__(self, other):
        if other is None or not other.is_a(JUMP):
            return False
        return self.target is other.target

    def __hash__(self):
        return super().__hash__()


class RET(IRStm):
    def __init__(self, exp):
        super().__init__()
        self.exp = exp

    def __str__(self):
        return "(RET {})".format(self.exp)

    def __eq__(self, other):
        if other is None or not other.is_a(RET):
            return False
        return self.exp == other.exp

    def __hash__(self):
        return super().__hash__()

    def kids(self):
        return self.exp.kids()


class MOVE(IRStm):
    def __init__(self, dst, src):
        super().__init__()
        self.dst = dst
        self.src = src

    def __str__(self):
        return '(MOVE {}, {})'.format(self.dst, self.src)

    def __eq__(self, other):
        if other is None or not other.is_a(MOVE):
            return False
        return self.dst == other.dst and self.src == other.src

    def __hash__(self):
        return super().__hash__()

    def kids(self):
        return self.dst.kids() + self.src.kids()


def conds2str(conds):
    if conds:
        cs = []
        for exp, boolean in conds:
            cs.append(str(exp) + ' == ' + str(boolean))
        return ' and '.join(cs)
    else:
        return 'None'


class PHIBase(IRStm):
    def __init__(self, var):
        super().__init__()
        assert var.is_a([TEMP, ATTR])
        self.var = var
        self.var.ctx = Ctx.STORE
        self.args = []
        self.defblks = []
        self.ps = []

    def _str_args(self):
        str_args = []
        if self.ps:
            #assert len(self.ps) == len(self.args)
            for arg, p in zip(self.args, self.ps):
                if arg:
                    str_args.append('{}?{}'.format(p, arg))
                else:
                    str_args.append('_')
        else:
            for arg in self.args:
                if arg:
                    str_args.append('{}'.format(arg))
                else:
                    str_args.append('_')
        return str_args

    def __eq__(self, other):
        if other is None or not other.is_a(PHIBase):
            return False
        return self.var == other.var

    def __hash__(self):
        return super().__hash__()

    def kids(self):
        kids = []
        for arg in self.args:
            kids += arg.kids()
        return self.var.kids() + kids

    def remove_arg(self, arg):
        idx = self.args.index(arg)
        if self.ps:
            assert len(self.args) == len(self.ps)
            self.ps.pop(idx)
        self.args.pop(idx)
        self.defblks.pop(idx)


class PHI(PHIBase):
    def __init__(self, var):
        super().__init__(var)

    def __str__(self):
        s = "(PHI '{}' <- phi[{}])".format(self.var, ", ".join(self._str_args()))
        return s


class UPHI(PHIBase):
    def __init__(self, var):
        super().__init__(var)

    def __str__(self):
        s = "(UPHI '{}' <- phi[{}])".format(self.var, ", ".join(self._str_args()))
        return s


def op2str(op):
    return op.__class__.__name__
