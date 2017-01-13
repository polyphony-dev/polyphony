import copy
from .symbol import Symbol
from .utils import is_a
from .env import env

op2sym_map = {
    'And':'and',
    'Or':'or',
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


class Ctx:
    LOAD=1
    STORE=2

    @classmethod
    def str(cls, ctx):
        sctx = ''
        if ctx & Ctx.LOAD:
            sctx += 'L'
        if ctx & Ctx.STORE:
            sctx += 'S'
        return sctx

class IR:
    def __init__(self):
        self.lineno = -1

    def __repr__(self):
        return self.__str__()

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
                if ir.is_a(TEMP):
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

    def __str__(self):
        return '{}{}'.format(op2sym_map[self.op], self.exp)

    def kids(self):
        return self.exp.kids()

class BINOP(IRExp):
    def __init__(self, op, left, right):
        super().__init__()
        self.op = op
        self.left = left
        self.right = right

    def __str__(self):
        return '({} {} {})'.format(self.left, op2sym_map[self.op], self.right)

    def kids(self):
        return self.left.kids() + self.right.kids()

class RELOP(IRExp):
    def __init__(self, op, left, right):
        super().__init__()
        self.op = op
        self.left = left
        self.right = right

    def __str__(self):
        return '({} {} {})'.format(self.left, op2sym_map[self.op], self.right)

    def kids(self):
        return self.left.kids() + self.right.kids()

class CALL(IRExp):
    def __init__(self, func, args):
        super().__init__()
        self.func = func
        self.args = args
        self.func_scope = None

    def __str__(self):
        s = '(CALL {}, '.format(self.func)
        s += ', '.join(map(str, self.args))
        s += ")"
        return s

    def kids(self):
        kids = []
        kids += self.func.kids()
        for arg in self.args:
            kids += arg.kids()
        return kids


class SYSCALL(IRExp):
    def __init__(self, name, args):
        super().__init__()
        self.name = name
        self.args = args
        self.has_ret = True

    def __str__(self):
        s = '(SYSCALL {}, '.format(self.name)
        s += ', '.join(map(str, self.args))
        s += ")"
        return s

    def kids(self):
        kids = []
        for arg in self.args:
            kids += arg.kids()
        return kids

    
class NEW(IRExp):
    def __init__(self, scope, args):
        super().__init__()
        self.func_scope = scope
        self.args = args

    def __str__(self):
        s = '(NEW {}, '.format(self.func_scope.orig_name)
        s += ', '.join(map(str, self.args))
        s += ")"
        return s

    def kids(self):
        kids = []
        for arg in self.args:
            kids += arg.kids()
        return kids


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
            return str(self.value)

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

    def kids(self):
        return [self]

    def symbol(self):
        return self.sym

    def set_symbol(self, sym):
        self.sym = sym

    def qualified_symbol(self):
        return (self.sym, )

class ATTR(IRExp):
    def __init__(self, exp, attr, ctx):
        super().__init__()
        self.exp = exp
        self.attr = attr
        self.ctx = ctx
        self.exp.ctx = Ctx.LOAD
        self.class_scope = None

    def __str__(self):
        return '{}.{}'.format(self.exp, self.attr)

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
            assert isinstance(self.exp.attr, Symbol)
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
        self.uses = []
        self.defs = []

    def add_use(self, u):
        self.uses.append(u)

    def add_def(self, d):
        self.defs.append(d)

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
        uses = ''
        if self.uses:
            uses = ', '.join([str(u) for u in self.uses])
        return '(CJUMP {}, {}, {})'.format(self.exp, self.true.name, self.false.name)


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
            
        uses = ''
        if self.uses:
            uses = ', '.join([str(u) for u in self.uses])
        return '(MCJUMP \n        {})'.format(', \n        '.join([item for item in items]))


class JUMP(IRStm):
    def __init__(self, target, typ = ''):
        super().__init__()
        self.target = target
        self.typ = typ # 'B': break, 'C': continue, 'L': loop-back, 'S': specific

    def __str__(self):
        return "(JUMP {} '{}')".format(self.target.name, self.typ)


class RET(IRStm):
    def __init__(self, exp):
        super().__init__()
        self.exp = exp

    def __str__(self):
        return "(RET {})".format(self.exp)

    def kids(self):
        return self.exp.kids()


class MOVE(IRStm):
    def __init__(self, dst, src):
        super().__init__()
        self.dst = dst
        self.src = src

    def __str__(self):
        return '(MOVE {}, {})'.format(self.dst, self.src)

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



