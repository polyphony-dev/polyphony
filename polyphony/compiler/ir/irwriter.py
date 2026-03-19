from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir.block import Block
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.types.type import Type


# Reverse maps from IrReader's maps
UNOP_RMAP = {'USub': '-', 'UAdd': '+', 'Not': '!', 'Invert': '~'}
BINOP_RMAP = {
    'And': 'and', 'Or': 'or',
    'Add': '+', 'Sub': '-', 'Mult': '*', 'FloorDiv': '/', 'Mod': 'mod',
    'LShift': '<<', 'RShift': '>>',
    'BitOr': '|', 'BitXor': '^', 'BitAnd': '&',
}
RELOP_RMAP = {
    'Eq': '==', 'NotEq': '!=', 'Lt': '<', 'LtE': '<=', 'Gt': '>', 'GtE': '>=',
    'IsNot': '!=',
}


class IrWriter(object):
    def __init__(self):
        self.lines: list[str] = []

    def write_scope(self, scope: Scope) -> str:
        self.lines = []
        self._write_scope_head(scope)
        if scope.entry_block:
            has_stms = any(blk.stms for blk in scope.traverse_blocks())
            if has_stms:
                self.lines.append('')
                self._write_all_blocks(scope)
        return '\n'.join(self.lines)

    def write_scopes(self, scopes: list[Scope]) -> str:
        parts = []
        for scope in scopes:
            parts.append(self.write_scope(scope))
        return '\n\n'.join(parts)

    def write_stm(self, stm: IrStm) -> str:
        return self._format_stm(stm)

    def write_exp(self, exp: IrExp) -> str:
        return self._format_exp(exp)

    def write_type(self, typ: Type) -> str:
        return self._format_type(typ)

    def _write_scope_head(self, scope: Scope):
        self.lines.append(f'scope {scope.name}')
        tags = ' '.join(sorted(scope.tags))
        self.lines.append(f'tags  {tags}')

        # params
        func = scope.as_function()
        if func:
            for sym in func.param_symbols(with_self=True):
                param_name = sym.name[len(Symbol.param_prefix) + 1:]
                typstr = self._format_type(sym.typ)
                tags = sym.tags - {'param'}
                if tags:
                    tagstr = ' '.join(sorted(tags))
                    self.lines.append(f'param {param_name}:{typstr} {{ {tagstr} }}')
                else:
                    self.lines.append(f'param {param_name}:{typstr}')

        # return type
        if func and func.return_type and not func.return_type.is_none():
            self.lines.append(f'return {self._format_type(func.return_type)}')

        # variables (exclude params, return, imported)
        if func:
            param_names = {s.name for s in func.param_symbols(with_self=True)}
            copy_names = set()
            for sym in func.param_symbols(with_self=True):
                copy_name = sym.name[len(Symbol.param_prefix) + 1:]
                copy_names.add(copy_name)
        else:
            param_names = set()
            copy_names = set()

        for name, sym in sorted(scope.symbols.items()):
            if name in param_names:
                continue
            if name in copy_names:
                continue
            if sym.name == Symbol.return_name:
                continue
            if sym.is_imported():
                continue
            typstr = self._format_type(sym.typ)
            tags = sym.tags.copy()
            if tags:
                tagstr = ' '.join(sorted(tags))
                self.lines.append(f'var {name}: {typstr} {{ {tagstr} }}')
            else:
                self.lines.append(f'var {name}: {typstr}')

        # imported symbols
        for name, sym in sorted(scope.symbols.items()):
            if not sym.is_imported():
                continue
            from_scope = sym.scope
            self.lines.append(f'from {from_scope.name} import {sym.name}')

    def _write_all_blocks(self, scope: Scope):
        for blk in scope.traverse_blocks():
            self._write_block(blk)
            self.lines.append('')

    def _write_block(self, blk: Block):
        self.lines.append(f'{blk.nametag}:')
        for stm in blk.stms:
            self.lines.append(self._format_stm(stm))

    def _format_stm(self, stm) -> str:
        match stm:
            case CMove():
                cond = self._format_exp(stm.cond)
                dst = self._format_exp(stm.dst)
                src = self._format_exp(stm.src)
                return f'mv? {cond} {dst} {src}'
            case Move():
                dst = self._format_exp(stm.dst)
                src = self._format_exp(stm.src)
                return f'mv {dst} {src}'
            case CExpr():
                cond = self._format_exp(stm.cond)
                exp = self._format_exp(stm.exp)
                return f'expr? {cond} {exp}'
            case Expr():
                exp = self._format_exp(stm.exp)
                return f'expr {exp}'
            case Jump():
                return f'j {stm.target.nametag}'
            case CJump():
                cond = self._format_exp(stm.exp)
                return f'cj {cond} {stm.true.nametag} {stm.false.nametag}'
            case MCJump():
                parts = []
                for cond, target in zip(stm.conds, stm.targets):
                    parts.append(self._format_exp(cond))
                    parts.append(target.nametag)
                return f'mj {" ".join(parts)}'
            case Ret():
                exp = self._format_exp(stm.exp)
                return f'ret {exp}'
            case LPhi():
                return self._format_phi('lphi', stm)
            case UPhi():
                return self._format_phi('uphi', stm)
            case Phi():
                return self._format_phi('phi', stm)
            case MStm():
                lines = ['mstm']
                for s in stm.stms:
                    lines.append(f'| {self._format_stm(s)}')
                return '\n'.join(lines)
            case _:
                raise ValueError(f'Unknown statement type: {type(stm)}')

    def _format_phi(self, keyword: str, stm) -> str:
        var = self._format_exp(stm.var)
        args_str = ' '.join(self._format_exp(a) for a in stm.args)
        result = f'{keyword} {var} ({args_str})'
        if stm.ps:
            ps_str = ' '.join(self._format_exp(p) for p in stm.ps)
            result += f' ({ps_str})'
        return result

    def _format_exp(self, exp) -> str:
        match exp:
            case Const():
                return self._format_const(exp)
            case Attr():
                return self._format_attr(exp)
            case Temp():
                return exp.name
            case UnOp():
                op = UNOP_RMAP[exp.op]
                inner = self._format_exp(exp.exp)
                return f'{op}{inner}'
            case BinOp():
                op = BINOP_RMAP[exp.op]
                left = self._format_exp(exp.left)
                right = self._format_exp(exp.right)
                return f'({op} {left} {right})'
            case RelOp():
                op = RELOP_RMAP[exp.op]
                left = self._format_exp(exp.left)
                right = self._format_exp(exp.right)
                return f'({op} {left} {right})'
            case Call():
                return self._format_callable('call', exp)
            case New():
                return self._format_callable('new', exp)
            case SysCall():
                return self._format_callable('syscall', exp)
            case MStore():
                mem = self._format_exp(exp.mem)
                offset = self._format_exp(exp.offset)
                val = self._format_exp(exp.exp)
                return f'(mst {mem} {offset} {val})'
            case MRef():
                mem = self._format_exp(exp.mem)
                offset = self._format_exp(exp.offset)
                return f'(mld {mem} {offset})'
            case Array():
                return self._format_array(exp)
            case CondOp():
                cond = self._format_exp(exp.cond)
                left = self._format_exp(exp.left)
                right = self._format_exp(exp.right)
                return f'(? {cond} {left} {right})'
            case PolyOp():
                op = BINOP_RMAP[exp.op]
                values = ' '.join(self._format_exp(v) for v in exp.values)
                return f'({op} [{values}])'
            case _:
                raise ValueError(f'Unknown expression type: {type(exp)}')

    def _format_const(self, c) -> str:
        if isinstance(c.value, bool):
            return str(c.value)
        elif isinstance(c.value, int):
            return str(c.value)
        elif isinstance(c.value, str):
            return f"'{c.value}'"
        else:
            return str(c.value)

    def _format_attr(self, attr) -> str:
        exp = self._format_exp(attr.exp)
        return f'{exp}.{attr.name}'

    def _format_callable(self, opcode: str, call) -> str:
        func = self._format_exp(call.func)
        parts = [func]
        for _, arg in call.args:
            parts.append(self._format_exp(arg))
        return f'({opcode} {" ".join(parts)})'

    def _format_array(self, arr) -> str:
        items = [self._format_exp(item) for item in arr.items]
        if arr.is_mutable:
            return f'[{" ".join(items)}]'
        else:
            return f'({" ".join(items)})'

    def _format_type(self, typ: Type) -> str:
        if typ.is_int():
            if typ.signed:
                return f'int{typ.width}'
            else:
                return f'bit{typ.width}'
        elif typ.is_bool():
            return 'bool'
        elif typ.is_str():
            return 'str'
        elif typ.is_list():
            elm = self._format_type(typ.element)
            if isinstance(typ.length, int) and typ.length != Type.ANY_LENGTH:
                return f'list<{elm}>[{typ.length}]'
            else:
                return f'list<{elm}>[]'
        elif typ.is_tuple():
            elm = self._format_type(typ.element)
            if typ.length != Type.ANY_LENGTH:
                return f'tuple<{elm}>[{typ.length}]'
            else:
                return f'tuple<{elm}>[]'
        elif typ.is_object():
            return f'object({typ.scope_name})'
        elif typ.is_class():
            return f'class({typ.scope_name})'
        elif typ.is_namespace():
            return f'namespace({typ.scope_name})'
        elif typ.is_function():
            return f'function({typ.scope_name})'
        elif typ.is_port():
            dtype_str = self._format_type(typ.dtype)
            root_sym = typ.root_symbol
            root_ref = f'{root_sym.scope.name}:{root_sym.name}'
            return f'port({typ.scope_name}, {dtype_str}, {typ.direction}, {typ.init}, {typ.assigned}, {root_ref})'
        elif typ.is_expr():
            exp_str = self._format_exp(typ.expr.exp)
            return f'expr({typ.scope_name}, {exp_str})'
        elif typ.is_none():
            return 'none'
        elif typ.is_undef():
            return 'undef'
        else:
            return str(typ)
