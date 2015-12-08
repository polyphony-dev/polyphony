
class IR:
    def __init__(self):
        self.lineno = -1
        self.col_offset = -1

    def is_(self, cls):
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
        return [self.exp]

    def clone(self):
        return UNOP(self.op, self.exp.clone())

class BINOP(IRExp):
    def __init__(self, op, left, right):
        super().__init__()
        self.op = op
        self.left = left
        self.right = right

    def __str__(self):
        return '(BINOP {}, {}, {})'.format(self.op, self.left, self.right)

    def kids(self):
        return [self.left, self.right]

    def clone(self):
        return BINOP(self.op, self.left.clone(), self.right.clone())

class RELOP(IRExp):
    def __init__(self, op, left, right):
        super().__init__()
        self.op = op
        self.left = left
        self.right = right

    def __str__(self):
        return '(RELOP {}, {}, {})'.format(self.op, self.left, self.right)

    def clone(self):
        return RELOP(self.op, self.left.clone(), self.right.clone())

class CALL(IRExp):
    def __init__(self, func, args, scope):
        super().__init__()
        self.func = func
        self.args = args
        self.func_scope = scope

    def __str__(self):
        s = '(CALL {}, '.format(self.func)
        s += ', '.join(map(str, self.args))
        s += ")"
        return s

    def clone(self):
        args = [arg.clone() for arg in self.args]
        return CALL(self.func.clone(), args, self.func_scope)

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
        return SYSCALL(self.name, args)

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
        return CONST(self.value)

class MREF(IRExp):
    def __init__(self, mem, offset, ctx):
        super().__init__()
        self.mem = mem
        self.offset = offset
        self.ctx = ctx

    def __str__(self):
        return '(MREF {}, {})'.format(self.mem, self.offset)

    def clone(self):
        return MREF(self.mem.clone(), self.offset.clone(), self.ctx)

class MSTORE(IRExp):
    def __init__(self, mem, offset, exp):
        super().__init__()
        self.mem = mem
        self.offset = offset
        self.exp = exp

    def __str__(self):
        return '(MSTORE {}, {}, {})'.format(self.mem, self.offset, self.exp)

    def clone(self):
        return MSTORE(self.mem.clone(), self.offset.clone(), self.exp.clone())

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
        return ARRAY([item.clone() for item in self.items])

class TEMP(IRExp):
    def __init__(self, sym, ctx):
        super().__init__()
        self.sym = sym
        self.ctx = ctx

    def __str__(self):
        if self.ctx == 'Store':
            ctx = 'S'
        else:
            ctx = 'L'

        return "'" + str(self.sym) + "'" + ctx

    def clone(self):
        return TEMP(self.sym, self.ctx)

class IRStm(IR):
    def __init__(self):
        super().__init__()
        self.uses = []
        self.defs = []
        self.block = None

    def add_use(self, u):
        self.uses.append(u)

    def add_def(self, d):
        self.defs.append(d)

    def program_order(self):
        return (self.block.order, self.block.stms.index(self))

class EXPR(IRStm):
    def __init__(self, exp):
        super().__init__()
        self.exp = exp

    def __str__(self):
        return '(EXPR {})'.format(self.exp)

    def clone(self):
        return EXPR(self.exp.clone())

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
        return '(CJUMP {}, {}, {} [{}])'.format(self.exp, self.true.name, self.false.name, uses)

    def clone(self):
        return CJUMP(self.exp.clone(), self.true, self.false)

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
        return '(MCJUMP {} [{}])'.format(', '.join([item for item in items]), uses)

    def clone(self):
        return MCJUMP(copy(self.conds), copy(self.targets))

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
        return "(JUMP {} '{}' [{}] {})".format(self.target.name, self.typ, uses, conds)

    def clone(self):
        jp = JUMP(self.target, self.typ)
        jp.uses = list(self.uses) if self.uses else None
        jp.conds = list(self.conds) if self.conds else None
        return jp

class RET(IRStm):
    def __init__(self, exp):
        super().__init__()
        self.exp = exp

    def __str__(self):
        return "(RET {})".format(self.exp)

    def clone(self):
        return RET(self.exp.clone())

class MOVE(IRStm):
    def __init__(self, dst, src):
        super().__init__()
        self.dst = dst
        self.src = src

    def __str__(self):
        return '(MOVE {}, {})'.format(self.dst, self.src)

    def clone(self):
        return MOVE(self.dst.clone(), self.src.clone())

def conds2str(conds):
    if conds:
        cs = []
        for exp, boolean in conds:
            cs.append(str(exp) + ' == ' + str(boolean))
        return ' and '.join(cs)
    else:
        return 'None'

class PHI(IRStm):
    def __init__(self, var, argc):
        super().__init__()
        assert isinstance(var, TEMP)
        self.var = var
        self.args = [None]*argc
        self.conds_list = None

    def __str__(self):
        args = []
        for arg in self.args:
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
        return [arg for arg in self.args if arg]

    def valid_conds(self):
        return [c for c in self.conds_list if c]

    def clone(self):
        return PHI(self.var.clone(), list(self.args), list(self.conds_list))

def op2str(op):
    return op.__class__.__name__

