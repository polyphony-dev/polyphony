import re
from collections import deque, defaultdict
from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir.irhelper import qualified_symbols
from polyphony.compiler.ir.block import Block
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.common.env import env


UNOP_MAP = {'-': 'USub', '+':'UAdd', '!':'Not', '~':'Invert'}
BINOP_MAP = {
    'and':'And', 'or':'Or',
    '+':'Add', '-':'Sub', '*':'Mult', '/':'FloorDiv', 'mod':'Mod',
    '<<':'LShift', '>>':'RShift',
    '|':'BitOr', '^':'BitXor', '&':'BitAnd',
    '!=':'IsNot',
}
RELOP_MAP = {
    '==':'Eq', '!=':'NotEq', '<':'Lt', '<=':'LtE', '>':'Gt', '>=':'GtE',
}

def check_int(s):
    if s[0] in ('-', '+'):
        return s[1:].isdigit()
    return s.isdigit()


class IRParser(object):
    def __init__(self, code: str):
        assert isinstance(code, str)
        self.current_scope: Scope = None  # type: ignore
        self.current_block: Block = None  # type: ignore
        self.lineno = 0
        self.lines = code.split('\n')
        self.current_lines = deque(self.lines)
        self.blocks = {}

    def peek_line(self) -> str:
        if not self.current_lines:
            return ''
        return self.current_lines[0].strip()

    def deq_line(self) -> str:
        self.lineno += 1
        return self.current_lines.popleft().strip()

    def skip_blank_line(self):
        while self.current_lines and self.peek_line() == '':
            self.deq_line()

    def is_end(self):
        return not self.current_lines

    def split(self, s, delim=' ', count=-1):
        results = filter(None, s.split(delim, count))
        return [r.strip() for r in results]

    def parse_scope(self):
        self.prepare_parse_scopes()
        for scope, current_lines in self.sources.items():
            self.current_lines = deque(current_lines)
            self.parse_early_scope_head()
            self.sources[scope] = list(self.current_lines)

        for scope, current_lines in self.sources.items():
            self.current_scope = env.scopes[scope]
            self.current_lines = deque(current_lines)
            self.parse_late_scope_head()
            self.skip_blank_line()
            if self.is_end():
                block = Block(self.current_scope, nametag='')
                self.current_scope.set_entry_block(block)
                self.current_scope.set_exit_block(block)
                continue
            self.parse_all_blocks()

    def prepare_parse_scopes(self):
        self.sources = defaultdict(list)
        current_lines = None
        for line in self.lines:
            tokens = self.split(line)
            if not tokens:
                continue
            if tokens[0] == 'scope':
                scope_name = tokens[1]
                current_lines = self.sources[scope_name]
            assert current_lines is not None
            current_lines.append(line)

    def parse_early_scope_head(self):
        self.skip_blank_line()
        line = self.peek_line()
        tokens = self.split(line)
        if tokens[0] != 'scope':
            raise
        # name
        name = tokens[1]
        names = name.rsplit('.', 1)
        if len(names) == 1:
            scope_name = names[0]
            outer_scope = None
        else:
            outer_scope = env.scopes[names[0]]
            scope_name = names[1]
        self.deq_line()
        scope_lineno = self.lineno

        # tags
        self.skip_blank_line()
        line = self.deq_line()
        tokens = self.split(line)
        if tokens[0] != 'tags':
            raise
        tags = {tag for tag in tokens[1:]}
        new_scope = Scope.create(outer_scope, scope_name, tags, scope_lineno)

    def _type_from_scope_tags(self, scope, tags: set):
        type_dict = {
            'namespace': Type.namespace,
            'class': Type.klass,
            'function': Type.function,
            'method': Type.function
        }
        for type_tag, typ in type_dict.items():
            if type_tag in tags:
                return typ(scope.name)
        raise

    def parse_late_scope_head(self):
        # params
        while True:
            self.skip_blank_line()
            if self.is_end():
                return
            line = self.peek_line()
            tokens = self.split(line, count=1)
            if tokens[0] != 'param':
                break
            name, rest = self.split(tokens[1], ':')
            rests = self.split(rest, '{')
            typstr = rests[0]
            t = self.parse_type(typstr)
            if len(rests) == 2:
                tagstr = rests[1]
                tagstr = tagstr.replace('}', '')
                tags = set(tagstr.split())
            else:
                tags = set()
            self.deq_line()
            if name == env.self_name:
                tags |= {'self'}
            param_in = self.current_scope.add_param_sym(name, tags=tags, typ=t)
            param_cp = self.current_scope.add_sym(name, tags=tags, typ=t)
            self.current_scope.add_param(param_in, None)

        # return type
        self.skip_blank_line()
        line = self.peek_line()
        tokens = self.split(line, count=1)
        if tokens[0] == 'return':
            typstr = tokens[1]
            if not self.current_scope.is_ctor():
                self.current_scope.tags.add('returnable')
            self.current_scope.return_type = self.parse_type(typstr)
            self.current_scope.add_return_sym(self.current_scope.return_type)
            line = self.deq_line()
        else:
            self.current_scope.return_type = Type.none()

        # symbols
        while True:
            self.skip_blank_line()
            if self.is_end():
                return
            line = self.peek_line()
            tokens = self.split(line, count=1)
            if tokens[0] != 'var':
                break

            name, rest = self.split(tokens[1], ':')
            rests = self.split(rest, '{')
            typstr = rests[0]
            t = self.parse_type(typstr)
            if len(rests) == 2:
                tagstr = rests[1]
                tagstr = tagstr.replace('}', '')
                tags = set(tagstr.split())
            else:
                tags = set()
            self.deq_line()
            self.current_scope.add_sym(name, tags=tags, typ=t)

    def parse_all_blocks(self):
        self.pre_parse_block()
        while True:
            self.parse_block()
            self.skip_blank_line()
            if self.is_end():
                return

    def pre_parse_block(self):
        self.skip_blank_line()
        for line in self.current_lines:
            tokens = self.split(line)
            if not tokens:
                continue
            if tokens[0][-1] != ':':
                continue
            block_name = tokens[0][:-1]
            block = Block(self.current_scope, nametag=block_name)
            if self.current_scope.entry_block is None:
                self.current_scope.set_entry_block(block)
            self.current_scope.set_exit_block(block)
            self.blocks[block_name] = block

    def parse_block(self):
        self.skip_blank_line()
        line = self.peek_line()
        line = line.strip()
        if line[-1] != ':':
            return
        self.deq_line()
        block_name = line[:-1]
        self.current_block = self.blocks[block_name]
        while self.parse_block_line():
            pass

    def parse_block_line(self) -> bool:
        self.skip_blank_line()
        if self.is_end():
            return False
        line = self.peek_line()
        tokens = self.split(line, count=1)
        op = tokens[0]
        if op[-1] == ':':  # block?
            return False
        stm = self.parse_stm(line)
        if not stm:
            print(stm)
        self.current_block.append_stm(stm)
        self.deq_line()
        return True

    def parse_stm(self, stmstr: str) -> IRStm:
        tokens = self.split(stmstr, count=1)
        op = tokens[0]
        operands = tokens[1]

        if op[-1] == '?':
            is_conditional = True
            op = op[:-1]
        else:
            is_conditional = False
        if op == 'mv':
            if is_conditional:
                return self.parse_cmv(operands)
            else:
                return self.parse_mv(operands)
        elif op == 'expr':
            if is_conditional:
                return self.parse_cexpr(operands)
            else:
                return self.parse_expr(operands)
        elif op == 'phi':
            return self.parse_phi(operands)
        elif op == 'j':
            return self.parse_jp(operands)
        elif op == 'cj':
            return self.parse_cj(operands)
        elif op == 'mj':
            return self.parse_mj(operands)
        elif op == 'ret':
            return self.parse_ret(operands)
        else:
            raise

    def walk_to_closing_paren(self, text, lparen, rparen):
        level = 1
        for i, c in enumerate(text):
            if c == lparen:
                level += 1
            elif c == rparen:
                level -= 1
            if level == 0:
                return text[:i].strip(), text[i+1:]
        raise

    def parse_operands(self, operands: str):
        text = operands
        ops = []
        while text:
            text = text.strip()
            m = re.match(r'[\+\-!~]?[@\w\.\d]+', text)
            if m:
                text = text[m.span()[1]:]
                ops.append(m.group(0))
                continue
            m = re.match(r'\(', text)
            if m:
                text = text[m.span()[1]:]
                body, remain = self.walk_to_closing_paren(text, '(', ')')
                ops.append(f'({body})')
                text = remain
                continue
            m = re.match(r'\[', text)
            if m:
                text = text[m.span()[1]:]
                body, remain = self.walk_to_closing_paren(text, '[', ']')
                ops.append(f'[{body}]')
                text = remain
                continue
            m = re.match(r'\'', text)
            if m:
                text = text[m.span()[1]:]
                i = text.find('\'')
                body, remain = text[:i], text[i+1:]
                ops.append(f'\'{body}\'')
                text = remain
                continue
            m = re.match(r'"', text)
            if m:
                text = text[m.span()[1]:]
                i = text.find('"')
                body, remain = text[:i], text[i+1:]
                ops.append(f'\'{body}\'')
                text = remain
                continue
            raise
        return ops

    def parse_mv(self, operands: str):
        ops = self.parse_operands(operands)
        if len(ops) != 2:
            raise
        dst_, src_ = ops
        dst = self.parse_dst(dst_)
        src = self.parse_exp(src_)
        return MOVE(dst, src)

    def parse_cmv(self, operands: str):
        ops = self.parse_operands(operands)
        if len(ops) != 3:
            raise
        cond_, dst_, src_ = ops
        cond = self.parse_exp(cond_)
        dst  = self.parse_dst(dst_)
        src  = self.parse_exp(src_)
        return CMOVE(cond, dst, src)

    def parse_expr(self, operands: str):
        ops = self.parse_operands(operands)
        if len(ops) != 1:
            raise
        exp = self.parse_exp(ops[0])
        return EXPR(exp)

    def parse_cexpr(self, operands: str):
        ops = self.parse_operands(operands)
        if len(ops) != 2:
            raise
        cond_, exp_ = ops
        cond = self.parse_exp(cond_)
        exp  = self.parse_exp(exp_)
        return CEXPR(cond, exp)

    def parse_phi(self, operands: str):
        raise

    def parse_jp(self, operands: str):
        if operands not in self.blocks:
            raise
        next_block = self.blocks[operands]
        self.current_block.connect(next_block)
        return JUMP(next_block)

    def parse_cj(self, operands: str):
        ops = self.parse_operands(operands)
        if len(ops) != 3:
            raise
        cond_, then_blk_, else_blk_ = ops
        cond = self.parse_scalar(cond_)
        if then_blk_ not in self.blocks:
            raise
        if else_blk_ not in self.blocks:
            raise
        then_blk = self.blocks[then_blk_]
        else_blk = self.blocks[else_blk_]
        self.current_block.connect(then_blk)
        self.current_block.connect(else_blk)
        return CJUMP(cond, then_blk, else_blk)

    def parse_mj(self, operands: str):
        ops = self.parse_operands(operands)
        assert len(ops) % 2 == 0
        conds = []
        targets = []
        for i in range(0, len(ops), 2):
            cond_, target_ = ops[i:i+2]
            cond = self.parse_scalar(cond_)
            conds.append(cond)
            if target_ not in self.blocks:
                raise
            blk = self.blocks[target_]
            targets.append(blk)
            self.current_block.connect(blk)
        return MCJUMP(conds, targets)

    def parse_ret(self, operands: str):
        ops = self.parse_operands(operands)
        if len(ops) != 1:
            raise
        self.current_scope.exit_block = self.current_block
        exp = self.parse_exp(ops[0])
        assert exp.is_a(TEMP)
        assert cast(TEMP, exp).name == Symbol.return_name
        return RET(exp)

    def parse_type(self, typstr: str) -> Type:
        if typstr.startswith('int'):
            width = int(typstr[3:])
            return Type.int(width, signed=True)
        elif typstr.startswith('bool'):
            return Type.bool()
        elif typstr.startswith('str'):
            return Type.str()
        elif typstr.startswith('bit'):
            width = int(typstr[3:])
            return Type.int(width, signed=False)
        elif typstr.startswith('list'):
            element = typstr[4:].strip()
            m = re.match(r'<(\w+)>\[(\d*)\]', element)
            assert m
            elm_t = self.parse_type(m.group(1))
            if m.group(2):
                length = int(m.group(2))
            else:
                length = Type.ANY_LENGTH
            return Type.list(elm_t, length)
        elif typstr.startswith('tuple'):
            element = typstr[5:].strip()
            m = re.match(r'<(\w+)>\[(\d*)\]', element)
            assert m
            elm_t = self.parse_type(m.group(1))
            if m.group(2):
                length = int(m.group(2))
            else:
                length = Type.ANY_LENGTH
            return Type.tuple(elm_t, length)
        elif typstr.startswith('object'):
            element = typstr[6:].strip()
            m = re.match(r'\((.*)\)', element)
            assert m
            return Type.object(m.group(1))
        elif typstr.startswith('class'):
            element = typstr[5:].strip()
            m = re.match(r'\((.*)\)', element)
            assert m
            return Type.klass(m.group(1))
        elif typstr.startswith('namespace'):
            element = typstr[9:].strip()
            m = re.match(r'\((.+)\)', element)
            assert m
            return Type.namespace(m.group(1))
        elif typstr.startswith('function'):
            element = typstr[8:].strip()
            m = re.match(r'\((.*)\)', element)
            assert m
            return Type.function(m.group(1), Type.undef(), tuple())
        elif typstr.startswith('port'):
            raise NotImplementedError()
        elif typstr.startswith('expr'):
            raise NotImplementedError()
        elif typstr.startswith('none'):
            return Type.none()
        elif typstr.startswith('undef'):
            return Type.undef()
        else:
            raise

    def is_var(self, token: str):
        return token[0].isalpha() or token[0] == '_' or token[0] == '@' or token[0] == '!' or token[0] == '$'

    def is_list(self, token: str):
        prefix = token[0]
        return prefix == '['

    def is_tuple(self, token: str):
        prefix = token[0]
        return prefix == '('

    def parse_exp(self, expstr: str) -> IRExp:
        if expstr[0] == '(':
            assert expstr[-1] == ')'
            exphead = expstr[1:-1].split()
            assert len(exphead) >= 1
            opcode = exphead[0]
            operands = expstr[1+len(opcode):-1]
            if opcode in BINOP_MAP:
                return self.parse_bin(opcode, operands)
            elif opcode in RELOP_MAP:
                return self.parse_rel(opcode, operands)
            elif opcode == 'call':
                return self.parse_call(operands)
            elif opcode == 'new':
                return self.parse_new(operands)
            elif opcode == 'syscall':
                return self.parse_syscall(operands)
            elif opcode == 'mld':
                return self.parse_mload(operands)
            elif opcode == 'mst':
                return self.parse_mstore(operands)
            else:
                # may be a tuple
                return self.parse_tuple(expstr)
        elif self.is_list(expstr):
            return self.parse_list(expstr)
        else:
            return self.parse_scalar(expstr)

    def parse_bin(self, op: str, operands: str):
        ops = self.parse_operands(operands)
        if len(ops) != 2:
            raise
        left_, right_ = ops
        left  = self.parse_exp(left_)
        right = self.parse_exp(right_)
        return BINOP(BINOP_MAP[op], left, right)

    def parse_rel(self, op: str, operands: str):
        ops = self.parse_operands(operands)
        if len(ops) != 2:
            raise
        left_, right_ = ops
        left  = self.parse_exp(left_)
        right = self.parse_exp(right_)
        return RELOP(RELOP_MAP[op], left, right)

    def parse_call(self, operands: str):
        ops = self.parse_operands(operands)
        args = []
        assert len(ops) > 0
        func = self.parse_var(ops[0])
        for arg_ in ops[1:]:
            arg = self.parse_exp(arg_)
            args.append(('', arg))
        return CALL(func, args, {})

    def parse_new(self, operands: str):
        ops = self.parse_operands(operands)
        args = []
        assert len(ops) > 0
        func = self.parse_var(ops[0])
        for arg_ in ops[1:]:
            arg = self.parse_exp(arg_)
            args.append(('', arg))
        return NEW(func, args, {})

    def parse_syscall(self, operands: str):
        # FIXME:
        ops = self.parse_operands(operands)
        args = []
        assert len(ops) > 0
        func = self.parse_var(ops[0])
        for arg_ in ops[1:]:
            arg = self.parse_exp(arg_)
            args.append(('', arg))
        return SYSCALL(func, args, {})

    def parse_mload(self, operands: str):
        ops = self.parse_operands(operands)
        if len(ops) != 2:
            raise
        mem_, offs_ = ops
        mem  = self.parse_var(mem_)
        offs = self.parse_exp(offs_)
        return MREF(mem, offs, Ctx.LOAD)

    def parse_mstore(self, operands: str):
        ops = self.parse_operands(operands)
        if len(ops) != 3:
            raise
        mem_, offs_, src_ = ops
        mem  = self.parse_var(mem_)
        offs = self.parse_exp(offs_)
        src  = self.parse_exp(src_)
        return MSTORE(mem, offs, src)

    def parse_list(self, s: str):
        m = re.match(r'\[(.*)\]', s)
        assert m
        items_ = m.group(1)
        items = []
        for item_ in self.split(items_):
            item = self.parse_exp(item_)
            items.append(item)
        return ARRAY(items, mutable=True)

    def parse_tuple(self, s: str):
        m = re.match(r'\((.*)\)', s)
        assert m
        items_ = m.group(1)
        items = []
        for item_ in self.parse_operands(items_):
            item = self.parse_exp(item_)
            items.append(item)
        return ARRAY(items, mutable=False)

    def parse_dst(self, dststr: str) -> IRVariable|ARRAY:
        if self.is_var(dststr):
            return self.parse_var(dststr, Ctx.STORE)
        elif self.is_tuple(dststr):
            return self.parse_tuple(dststr)
        else:
            raise

    def parse_var(self, varstr: str, ctx: Ctx = Ctx.LOAD) -> IRVariable:
        assert self.is_var(varstr)
        names = varstr.split('.')
        var = TEMP(names[0])
        # If IRParser methods are used partially, current_scope may be None
        if self.current_scope and self.current_scope.is_closure():
            # check if the variable is free variable
            sym = qualified_symbols(var, self.current_scope)[-1]
            if isinstance(sym, Symbol):
                if sym.scope is not self.current_scope and not sym.scope.is_namespace():
                    sym.add_tag('free')
                    assert sym.scope.is_enclosure()
                    sym.scope.add_closure(self.current_scope)
        for name in names[1:]:
            var = ATTR(var, name)
        var.ctx = ctx
        return var

    def parse_scalar(self, s: str) -> IRExp:
        if s == 'True' or s == 'False':
            return CONST(s == 'True')
        if self.is_var(s):
            return self.parse_var(s, Ctx.LOAD)
        prefix = s[0]
        if self.is_unop(prefix):
            irop = UNOP_MAP[prefix]
            exp = self.parse_scalar(s[1:])
            return UNOP(irop, exp)
        elif s.isdigit():
            return CONST(int(s))
        elif s.startswith('"') and s.endswith('"') or s.startswith("'") and s.endswith("'"):
            return CONST(s[1:-1])
        else:
            return CONST(s)

    def is_unop(self, op):
        return op in ('+', '-', '!', '~')

    def is_binop(self, op):
        return op in ('+', '-', '*', '/', 'mod',
                         '^', '|', '&',
                         '<<', '>>')

    def is_relop(self, op):
        return op in ('==', '!=', '<=', '>=', '<', '>',
                         'and', 'or')


def ir_stm(scope: Scope, code: str):
    parser = IRParser('')
    parser.current_scope = scope
    return parser.parse_stm(code)
