import copy
from .symbol import Symbol

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

    def is_(self, cls):
        return isinstance(self, cls)

    def __repr__(self):
        return self.__str__()

    def is_jump(self):
        return False

    def is_a(self, cls):
        if isinstance(cls, list) or isinstance(cls, tuple):
            for c in cls:
                if isinstance(self, c):
                    return True
            return False
        else:
            return isinstance(self, cls)

class IRExp(IR):
    def __init__(self):
        super().__init__()

class UNOP(IRExp):
    def __init__(self, op, exp):
        super().__init__()
        self.op = op
        self.exp = exp

    def __str__(self):
        return '(UNOP {}, {})'.format(self.op, self.exp)

    def kids(self):
        return self.exp.kids()

    def clone(self):
        ir = UNOP(self.op, self.exp.clone())
        ir.lineno = self.lineno
        return ir

class BINOP(IRExp):
    def __init__(self, op, left, right):
        super().__init__()
        self.op = op
        self.left = left
        self.right = right

    def __str__(self):
        return '(BINOP {}, {}, {})'.format(self.op, self.left, self.right)

    def kids(self):
        return self.left.kids() + self.right.kids()

    def clone(self):
        ir = BINOP(self.op, self.left.clone(), self.right.clone())
        ir.lineno = self.lineno
        return ir

class RELOP(IRExp):
    def __init__(self, op, left, right):
        super().__init__()
        self.op = op
        self.left = left
        self.right = right

    def __str__(self):
        return '(RELOP {}, {}, {})'.format(self.op, self.left, self.right)

    def clone(self):
        ir = RELOP(self.op, self.left.clone(), self.right.clone())
        ir.lineno = self.lineno
        return ir

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

    def clone(self):
        args = [arg.clone() for arg in self.args]
        ir = CALL(self.func.clone(), args)
        ir.lineno = self.lineno
        return ir

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

    def clone(self):
        args = [arg.clone() for arg in self.args]
        ir = SYSCALL(self.name, args)
        ir.lineno = self.lineno
        return ir

    def kids(self):
        kids = []
        for arg in self.args:
            kids += arg.kids()
        return kids

class CTOR(IRExp):
    def __init__(self, scope, args):
        super().__init__()
        self.func_scope = scope
        self.args = args

    def __str__(self):
        s = '(CTOR {}, '.format(self.func_scope.orig_name)
        s += ', '.join(map(str, self.args))
        s += ")"
        return s

    def clone(self):
        args = [arg.clone() for arg in self.args]
        ir = CTOR(self.func_scope, args)
        ir.lineno = self.lineno
        return ir

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

    def clone(self):
        ir = CONST(self.value)
        ir.lineno = self.lineno
        return ir

    def kids(self):
        return [self]

class MREF(IRExp):
    def __init__(self, mem, offset, ctx):
        super().__init__()
        self.mem = mem
        self.offset = offset
        self.ctx = ctx

    def __str__(self):
        return '(MREF {}, {})'.format(self.mem, self.offset)

    def clone(self):
        ir = MREF(self.mem.clone(), self.offset.clone(), self.ctx)
        ir.lineno = self.lineno
        return ir

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

    def clone(self):
        ir = MSTORE(self.mem.clone(), self.offset.clone(), self.exp.clone())
        ir.lineno = self.lineno
        return ir

    def kids(self):
        return self.mem.kids() + self.offset.kids() + self.exp.kids()

class ARRAY(IRExp):
    def __init__(self, items):
        super().__init__()
        self.items = items

    def __str__(self):
        s = "(ARRAY "
        if len(self.items) > 8:
            s += ', '.join(map(str, self.items[:10]))
            s += '...'
        else:
            s += ', '.join(map(str, self.items))
        s += ")"
        return s

    def clone(self):
        ir = ARRAY([item.clone() for item in self.items])
        ir.lineno = self.lineno
        return ir

    def kids(self):
        kids = []
        for item in self.items:
            kids += item.kids()
        return kids

class TEMP(IRExp):
    def __init__(self, sym, ctx):
        super().__init__()
        self.sym = sym
        self.ctx = ctx
        assert isinstance(ctx, int)

    def __str__(self):
        return str(self.sym) + ':' + Ctx.str(self.ctx)

    def clone(self):
        ir = TEMP(self.sym, self.ctx)
        ir.lineno = self.lineno
        return ir

    def kids(self):
        return [self]

class ATTR(IRExp):
    def __init__(self, exp, attr, ctx):
        super().__init__()
        self.exp = exp
        self.attr = attr
        self.ctx = ctx
        self.exp.ctx = ctx
        self.scope = None

    def __str__(self):
        return '{}.{}:'.format(self.exp, self.attr, Ctx.str(self.ctx))

    def clone(self):
        ir = ATTR(self.exp.clone(), self.attr, self.ctx)
        ir.lineno = self.lineno
        return ir

    def kids(self):
        return [self]

    def head(self):
        if self.exp.is_a(ATTR):
            return self.exp.head()
        return self.exp.sym

    def tail(self):
        if self.exp.is_a(ATTR):
            assert isinstance(self.exp.attr, Symbol)
            return self.exp.attr
        return self.exp.sym

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

    def clone(self):
        ir = EXPR(self.exp.clone())
        ir.lineno = self.lineno
        return ir

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
        return '(CJUMP {}, {}::{}, {}::{} [{}])'.format(self.exp, self.true.name, self.true.group.name, self.false.name, self.false.group.name, uses)

    def clone(self):
        ir = CJUMP(self.exp.clone(), self.true, self.false)
        ir.lineno = self.lineno
        return ir

    def is_jump(self):
        return True

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
            items.append('({}) => {}::{}'.format(cond, target.name, target.group.name))
            
        uses = ''
        if self.uses:
            uses = ', '.join([str(u) for u in self.uses])
        return '(MCJUMP \n        {}\n        [{}])'.format(', \n        '.join([item for item in items]), uses)

    def clone(self):
        ir = MCJUMP()
        ir.conds = [cond.clone() for cond in self.conds]
        ir.targets = copy.copy(self.targets)
        ir.lineno = self.lineno
        return ir

    def is_jump(self):
        return True

class JUMP(IRStm):
    def __init__(self, target, typ = ''):
        super().__init__()
        self.target = target
        self.typ = typ # 'B': break, 'C': continue, 'L': loop-back, 'S': specific
        self.uses = None
        self.conds = None

    def __str__(self):
        uses = ''
        if self.uses:
            uses = ', '.join([str(u) for u in self.uses])
        conds = conds2str(self.conds)
        return "(JUMP {}::{} '{}' [{}] {})".format(self.target.name, self.target.group.name, self.typ, uses, conds)

    def clone(self):
        jp = JUMP(self.target, self.typ)
        jp.uses = list(self.uses) if self.uses else None
        jp.conds = list(self.conds) if self.conds else None
        jp.lineno = self.lineno
        return jp

    def is_jump(self):
        return True

class RET(IRStm):
    def __init__(self, exp):
        super().__init__()
        self.exp = exp

    def __str__(self):
        return "(RET {})".format(self.exp)

    def clone(self):
        ir = RET(self.exp.clone())
        ir.lineno = self.lineno
        return ir

    def kids(self):
        return self.exp.kids()

class MOVE(IRStm):
    def __init__(self, dst, src):
        super().__init__()
        self.dst = dst
        self.src = src

    def __str__(self):
        return '(MOVE {}, {})'.format(self.dst, self.src)

    def clone(self):
        ir = MOVE(self.dst.clone(), self.src.clone())
        ir.lineno = self.lineno
        return ir

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

class PHI(IRStm):
    def __init__(self, var):
        super().__init__()
        assert isinstance(var, TEMP)
        self.var = var
        self.args = []
        self.conds_list = None

    def __str__(self):
        args = []
        for arg, blk in self.args:
            if arg:
                args.append(str(arg))
            else:
                args.append('_')
        s = "(PHI '{}' <- phi[{}])".format(self.var, ", ".join(args))
        if self.conds_list:
            assert len(self.conds_list) == len(self.args)
            c = ''
            for conds in self.conds_list:
                c += '    ' + conds2str(conds) + '\n'
            c = c[:-1] #remove last LF
            s += '\n'+c
        return s

    def argv(self):
        return [arg for arg, blk in self.args if arg]

    def valid_conds(self):
        return [c for c in self.conds_list if c]

    def clone(self):
        #ir = PHI(self.var.clone(), [(arg.clone(), blk) for arg, blk in self.args], list(self.conds_list))
        ir = PHI(self.var.clone())
        for arg, blk in self.args:
            ir.args.append((arg.clone(), blk))
        ir.lineno = self.lineno
        return ir

    def kids(self):
        kids = []
        for arg in self.args:
            kids += arg.kids()
        return self.var.kids() + kids

def op2str(op):
    return op.__class__.__name__

