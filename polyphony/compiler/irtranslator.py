import ast
import copy
import os
import builtins as python_builtins
from .block import Block
from .builtin import builtin_symbols, append_builtin
from .builtin import lib_port_type_names
from .common import fail
from .env import env
from .errors import Errors
from .ir import *
from .irhelper import op2str, eval_unop
from .scope import Scope, FunctionParam
from .symbol import Symbol
from .type import Type
from logging import getLogger
logger = getLogger(__name__)

INTERNAL_FUNCTION_DECORATORS = [
    'mutable',
    'inlinelib',
    'builtin',
    'decorator',
    'predicate',
]
INTERNAL_CLASS_DECORATORS = [
    'builtin',
    'typeclass',
]
BUILTIN_PACKAGES = (
    'polyphony',
    'polyphony.typing',
    'polyphony.io',
    'polyphony.timing',
    'polyphony.verilog',
)

ignore_packages = []


class ImportVisitor(ast.NodeVisitor):
    def __init__(self, target_scope):
        self.target_scope = target_scope

    def _load_subfile(self, name):
        from .common import read_source
        dirname = os.path.dirname(env.current_filename)
        filename = '{}{}{}.py'.format(dirname, os.path.sep, name)

        if not os.path.isfile(filename):
            filename = filename.lstrip('.')
            filename = '{}{}'.format(os.getcwd(), filename)
            if not os.path.isfile(filename):
                return False
        if name in env.scopes:
            return True
        cur_filename = env.current_filename
        env.set_current_filename(filename)
        namespace = Scope.create_namespace(None, name, set())
        env.push_outermost_scope(namespace)
        for sym in builtin_symbols.values():
            namespace.import_sym(sym)
        translator = IRTranslator()
        translator.translate(read_source(filename), '', top=namespace)
        env.pop_outermost_scope()
        env.set_current_filename(cur_filename)
        return True

    def visit_Import(self, node):
        for nm in node.names:
            if nm.name not in BUILTIN_PACKAGES:
                if self._load_subfile(nm.name):
                    pass
                else:
                    if nm.asname:
                        ignore_packages.append(nm.asname)
                    else:
                        ignore_packages.append(nm.name)
                    continue

            target_namespace = env.scopes[nm.name]
            if nm.asname:
                sym = self.target_scope.gen_sym(nm.asname)
            else:
                nms = nm.name.split('.')
                parent = self.target_scope
                for n in nms[:-1]:
                    if not parent.has_sym(n):
                        sym = parent.gen_sym(n)
                        scope = Scope.create_namespace(parent, n, set())
                        sym.set_type(Type.namespace(scope))
                        parent = scope
                    else:
                        sym = parent.find_sym(n)
                        parent = sym.typ.get_scope()
                name = nms[-1]
                sym = parent.gen_sym(name)
            sym.set_type(Type.namespace(target_namespace))

    def visit_ImportFrom(self, node):
        def import_to_scope(imp_sym, asname=None):
            if asname:
                sym = self.target_scope.inherit_sym(imp_sym, asname)
            else:
                sym = self.target_scope.inherit_sym(imp_sym, imp_sym.name)

        if node.module not in BUILTIN_PACKAGES:
            if self._load_subfile(node.module):
                pass
            else:
                # print("WARNING: Unsupported module '{}'".format(node.module))
                for nm in node.names:
                    if nm.asname:
                        ignore_packages.append(nm.asname)
                    else:
                        ignore_packages.append(nm.name)
                return
        from_scope = env.scopes[node.module]
        for nm in node.names:
            if nm.name == '*':
                for imp_name in from_scope.all_imports:
                    imp_sym = from_scope.find_sym(imp_name)
                    import_to_scope(imp_sym)
                break
            else:
                imp_sym = from_scope.find_sym(nm.name)
                if not imp_sym:
                    fail((self.target_scope, node.lineno), Errors.CANNOT_IMPORT, [nm.name])
                import_to_scope(imp_sym, nm.asname)


class ScopeVisitor(ast.NodeVisitor):
    def __init__(self, top_scope):
        self.current_scope = top_scope
        self.annotation_visitor = AnnotationVisitor(self)
        self.decorator_visitor = DecoratorVisitor(self)

    def _leave_scope(self, outer_scope):
        # override it if already exists
        outer_scope.del_sym(self.current_scope.orig_name)
        if self.current_scope.is_class():
            t = Type.klass(self.current_scope)
        else:
            t = Type.function(self.current_scope, None, None)
        outer_scope.add_sym(self.current_scope.orig_name, typ=t)
        self.current_scope = outer_scope

    def visit_FunctionDef(self, node):
        def _make_param_symbol(arg, is_vararg=False):
            if arg.annotation:
                ann = self.annotation_visitor.visit(arg.annotation)
                is_lib = self.current_scope.is_lib()
                param_t = Type.from_annotation(ann, self.current_scope, is_lib)
                if not param_t:
                    fail((self.current_scope, node.lineno), Errors.UNKNOWN_TYPE_NAME, (ann,))
            else:
                param_t = Type.int()
            param_in = self.current_scope.add_param_sym(arg.arg, typ=param_t)
            param_copy = self.current_scope.add_sym(arg.arg, typ=param_t.clone())
            if is_vararg:
                param_t.set_vararg(True)
            return param_in, param_copy

        outer_scope = self.current_scope

        synth_params = None
        tags = set()
        for deco in node.decorator_list:
            deco_info = self.decorator_visitor.visit(deco)
            if isinstance(deco_info, str):
                deco_name = deco_info
            elif isinstance(deco_info, tuple):
                deco_name = deco_info[0]
                deco_args = deco_info[1]
                deco_kwargs = deco_info[2]
            else:
                assert False
            sym = self.current_scope.find_sym(deco_name)
            if sym and sym.typ.is_function() and sym.typ.get_scope().is_decorator():
                if sym.typ.get_scope().name == 'polyphony.rule':
                    synth_params = deco_kwargs
                elif sym.typ.get_scope().name == 'polyphony.pure':
                    if not env.config.enable_pure:
                        fail((outer_scope, node.lineno), Errors.PURE_IS_DISABLED)
                    tags.add(sym.typ.get_scope().orig_name)
                else:
                    tags.add(sym.typ.get_scope().orig_name)
            elif deco_name in INTERNAL_FUNCTION_DECORATORS:
                tags.add(deco_name)
            else:
                fail((outer_scope, node.lineno), Errors.UNSUPPORTED_DECORATOR, [deco_name])
        if outer_scope.is_class() and 'classmethod' not in tags:
            tags.add('method')
            if node.name == '__init__':
                tags.add('ctor')
            elif node.name == '__call__':
                tags.add('callable')
        else:
            tags.add('function')
        if outer_scope.is_lib() and 'inlinelib' not in tags:
            tags.add('lib')

        self.current_scope = Scope.create(outer_scope, node.name, tags, node.lineno)
        if synth_params:
            self.current_scope.synth_params.update(synth_params)
        for arg in node.args.args:
            param_in, param_copy = _make_param_symbol(arg)
            self.current_scope.add_param(param_in, param_copy, None)
        if node.args.vararg:
            param_in, param_copy = _make_param_symbol(node.args.vararg, is_vararg=True)
            self.current_scope.add_param(param_in, param_copy, None)
        if node.returns:
            ann = self.annotation_visitor.visit(node.returns)
            is_lib = self.current_scope.is_lib()
            t = Type.from_annotation(ann, self.current_scope, is_lib)
            if t:
                self.current_scope.return_type = t
                if t is not Type.none_t:
                    self.current_scope.add_tag('returnable')
            else:
                fail((self.current_scope, node.lineno), Errors.UNKNOWN_TYPE_NAME, [ann])

        if self.current_scope.is_method():
            if (not self.current_scope.params or
                    not self.current_scope.params[0].sym.is_param()):
                fail((self.current_scope, node.lineno), Errors.METHOD_MUST_HAVE_SELF)
            first_param = self.current_scope.params[0]
            self_typ = Type.object(outer_scope)
            first_param.copy.set_type(self_typ)
            first_param.sym.set_type(self_typ)
            first_param.copy.add_tag('self')
            first_param.sym.add_tag('self')

        if self.current_scope.is_builtin():
            append_builtin(outer_scope, self.current_scope)
        if self.current_scope.is_lib() and not self.current_scope.is_inlinelib():
            pass
        elif self.current_scope.is_pure():
            if self.current_scope.is_method() and not self.current_scope.parent.is_module():
                fail((outer_scope, node.lineno), Errors.PURE_CTOR_MUST_BE_MODULE)
            pass
        elif self.current_scope.is_testbench() and outer_scope is not Scope.global_scope():
            pass
        else:
            for stm in node.body:
                self.visit(stm)
        self._leave_scope(outer_scope)

    def visit_ClassDef(self, node):
        outer_scope = self.current_scope
        if outer_scope.is_function():
            fail((outer_scope, node.lineno), Errors.LOCAL_CLASS_DEFINITION_NOT_ALLOWED)

        tags = set()
        for deco in node.decorator_list:
            deco_name = self.decorator_visitor.visit(deco)
            sym = self.current_scope.find_sym(deco_name)
            if sym and sym.typ.is_function() and sym.typ.get_scope().is_decorator():
                tags.add(sym.typ.get_scope().orig_name)
            elif deco_name in INTERNAL_CLASS_DECORATORS:
                tags.add(deco_name)
            else:
                fail((outer_scope, node.lineno), Errors.UNSUPPORTED_DECORATOR, [deco_name])
        scope_qualified_name = (outer_scope.name + '.' + node.name)
        if scope_qualified_name in lib_port_type_names:
            tags |= {'port', 'lib'}
        if outer_scope.name == 'polyphony.typing':
            tags |= {'typeclass', 'lib'}
        if outer_scope.is_lib() and 'inlinelib' not in tags:
            tags.add('lib')
        self.current_scope = Scope.create(outer_scope,
                                          node.name,
                                          tags | {'class'},
                                          node.lineno)

        for base in node.bases:
            base_name = self.visit(base)
            base_sym = outer_scope.find_sym(base_name)
            assert base_sym.typ.is_class()
            base_scope = base_sym.typ.get_scope()
            for sym in base_scope.symbols.values():
                self.current_scope.import_sym(sym)
            self.current_scope.bases.append(base_scope)

        if self.current_scope.is_module():
            for m in ['append_worker']:
                scope = Scope.create(self.current_scope, m, {'method', 'lib'}, node.lineno)
                sym = self.current_scope.add_sym(m, typ=Type.function(scope, None, None))
                blk = Block(scope)
                scope.set_entry_block(blk)
                scope.set_exit_block(blk)

        if self.current_scope.is_builtin():
            append_builtin(outer_scope, self.current_scope)

        for stm in node.body:
            self.visit(stm)

        self._leave_scope(outer_scope)


class CompareTransformer(ast.NodeTransformer):
    '''Transform 'v0 op v1 op v2' to 'v0 op v1 and v1 op v2' '''
    def visit_Compare(self, node):
        if len(node.ops) > 1:
            compares = []
            compares.append(ast.Compare(left=node.left,
                                        ops=node.ops[0:1],
                                        comparators=node.comparators[0:1]))
            l = node.comparators[0]
            for op, right in zip(node.ops[1:], node.comparators[1:]):
                compares.append(ast.Compare(left=l, ops=[op], comparators=[right]))
                l = right
            andexpr = ast.BoolOp(op=ast.And(), values=compares)
            return ast.copy_location(andexpr, node)
        else:
            return node


class AugAssignTransformer(ast.NodeTransformer):
    '''Transform 'v0 += v1' to 'v0 = v0 + v1' '''
    def visit_AugAssign(self, node):
        lhs = copy.copy(node.target)
        lhs.ctx = ast.Load()
        binop = ast.BinOp(op=node.op, left=lhs, right=node.value)
        assign = ast.Assign(targets=[node.target], value=binop)
        return ast.copy_location(assign, node)


class CodeVisitor(ast.NodeVisitor):
    def __init__(self, top_scope, type_comments):
        self.current_scope = top_scope
        self.type_comments = type_comments

        self.current_block = Block(self.current_scope)
        if self.current_scope.entry_block is None:
            self.current_scope.set_entry_block(self.current_block)
        else:
            self.current_scope.entry_block.connect(self.current_block)
        self.function_exit = None

        self.loop_bridge_blocks = []
        self.loop_end_blocks = []

        self.nested_if = False
        self.last_node = None

        self.annotation_visitor = AnnotationVisitor(self)
        self.lazy_defs = []
        self.current_with_blk_synth_params = {}
        self.current_loop_synth_params = {}
        self.invisible_symbols = set()

    def emit(self, stm, ast_node):
        self.current_block.append_stm(stm)
        stm.lineno = ast_node.lineno
        self.last_node = ast_node

    def emit_to(self, block, stm, ast_node):
        block.append_stm(stm)
        stm.lineno = ast_node.lineno
        self.last_node = ast_node

    def _nodectx2irctx(self, node):
        if isinstance(node.ctx, ast.Store) or isinstance(node.ctx, ast.AugStore):
            return Ctx.STORE
        else:
            return Ctx.LOAD

    def _needJUMP(self, block):
        if not block.preds:
            return False
        if not block.stms:
            return True
        last = block.stms[-1]
        return not last.is_a(JUMP) and \
            not (last.is_a(MOVE) and last.dst.is_a(TEMP) and last.dst.sym.is_return())

    def _new_block(self, scope, nametag='b'):
        blk = Block(scope, nametag)
        blk.synth_params.update(scope.synth_params)
        blk.synth_params.update(self.current_with_blk_synth_params)
        blk.synth_params.update(self.current_loop_synth_params)
        return blk

    def _tmp_block(self, scope):
        return self._new_block(scope, 'tmp')

    def _enter_scope(self, name):
        outer_scope = self.current_scope
        self.current_scope = env.scopes[outer_scope.name + '.' + name]

        last_block = self.current_block
        new_block = self._new_block(self.current_scope)
        self.current_scope.set_entry_block(new_block)
        self.current_scope.set_exit_block(new_block)
        self.current_block = new_block
        self.current_param_stms = []
        self.invisible_symbols.clear()

        return (outer_scope, last_block)

    def _leave_scope(self, outer_scope, last_block):
        self._visit_lazy_defs()
        if self.current_scope.exit_block is None:
            self.current_scope.exit_block = self.current_scope.entry_block
        self.current_scope = outer_scope
        self.current_block = last_block

    def _visit_lazy_defs(self):
        lazy_defs = self.lazy_defs[:]
        self.lazy_defs = []
        for lazy_def in lazy_defs:
            if isinstance(lazy_def, ast.FunctionDef):
                self._visit_lazy_FunctionDef(lazy_def)
            elif isinstance(lazy_def, ast.ClassDef):
                self._visit_lazy_ClassDef(lazy_def)

    def visit_Module(self, node):
        for stm in node.body:
            self.visit(stm)
        self._visit_lazy_defs()

    def visit_FunctionDef(self, node):
        self.lazy_defs.append(node)

    def _visit_lazy_FunctionDef(self, node):
        context = self._enter_scope(node.name)
        outer_function_exit = self.function_exit
        self.function_exit = self._tmp_block(self.current_scope)
        if self.current_scope.is_method():
            params = self.current_scope.params[1:]  # skip 'self'
        else:
            params = self.current_scope.params
        for idx, param in enumerate(params):
            mv = MOVE(TEMP(param.copy, Ctx.STORE),
                      TEMP(param.sym, Ctx.LOAD))
            self.emit(mv, node)
            self.current_param_stms.append(mv)
        skip = len(node.args.args) - len(node.args.defaults)
        for idx, (param, defval) in enumerate(zip(self.current_scope.params[skip:],
                                                  node.args.defaults)):
            if param.sym.typ.is_seq():
                fail((self.current_scope, node.lineno), Erroes.UNSUPPORTED_DEFAULT_SEQ_PARAM)
            d = self.visit(defval)
            self.current_scope.params[skip + idx] = FunctionParam(param.sym, param.copy, d)

        if self.current_scope.is_lib() and not self.current_scope.is_inlinelib():
            self._leave_scope(*context)
            return
        if self.current_scope.is_pure():
            PureScopeVisitor(self.current_scope, self.type_comments).visit(node)
            self._leave_scope(*context)
            return
        if self.current_scope.is_testbench() and env.outermost_scope() is not Scope.global_scope():
            return
        for stm in node.body:
            self.visit(stm)
        if self._needJUMP(self.current_block):
            self.emit(JUMP(self.function_exit), node)
            self.current_block.connect(self.function_exit)

        if self.current_scope.has_sym(Symbol.return_prefix):
            sym = self.current_scope.find_sym(Symbol.return_prefix)
        else:
            sym = self.current_scope.add_return_sym()
        if self.function_exit.preds:
            function_exit = self._new_block(self.current_scope, 'exit')
            self.current_scope.replace_block(self.function_exit, function_exit)
            self.function_exit = function_exit
            self.current_scope.set_exit_block(self.function_exit)
            if self.last_node:
                self.emit_to(self.function_exit, RET(TEMP(sym, Ctx.LOAD)), self.last_node)
        else:
            self.current_scope.set_exit_block(self.current_block)
        self.function_exit = outer_function_exit
        self._leave_scope(*context)

    def visit_AsyncFunctionDef(self, node):
        fail((self.current_scope, node.lineno), Errors.UNSUPPORTED_SYNTAX, ['async def statement'])

    def visit_ClassDef(self, node):
        self.lazy_defs.append(node)

    def _visit_lazy_ClassDef(self, node):
        context = self._enter_scope(node.name)
        for body in node.body:
            self.visit(body)
        logger.debug(node.name)
        if not self.current_scope.is_typeclass() and not any([method.is_ctor() for method in self.current_scope.children]):
            tags = {'method', 'ctor'}
            if self.current_scope.parent.is_lib():
                tags |= {'lib'}
            ctor = Scope.create(self.current_scope, '__init__', tags, node.lineno)
            # add 'self' parameter
            param_t = Type.object(self.current_scope)
            param_in = ctor.add_param_sym(env.self_name, typ=param_t)
            param_copy = ctor.add_sym(env.self_name, typ=param_t)
            ctor.add_param(param_in, param_copy, None)
            # add empty block
            blk = self._new_block(ctor)
            ctor.set_entry_block(blk)
            ctor.set_exit_block(blk)
            # add necessary symbol
            ctor.add_return_sym()

        self.current_scope.set_exit_block(self.current_block)
        self._leave_scope(*context)

    def visit_Return(self, node):
        #TODO multiple return value
        if self.current_scope.has_sym(Symbol.return_prefix):
            sym = self.current_scope.find_sym(Symbol.return_prefix)
        else:
            sym = self.current_scope.add_return_sym()
        ret = TEMP(sym, Ctx.STORE)
        if node.value:
            self.emit(MOVE(ret, self.visit(node.value)), node)
            self.current_scope.add_tag('returnable')
        self.emit(JUMP(self.function_exit, 'E'), node)

        self.current_block.connect(self.function_exit)

    def visit_Delete(self, node):
        fail((self.current_scope, node.lineno), Errors.UNSUPPORTED_SYNTAX, ['del statement'])

    def visit_Assign(self, node):
        tail_lineno = _get_tail_lineno(node.value)
        right = self.visit(node.value)
        for target in node.targets:
            left = self.visit(target)
            if left.is_a(TEMP) and left.symbol().name == '__all__':
                if right.is_a(ARRAY):
                    self.current_scope.all_imports = []
                    for item in right.items:
                        if not (item.is_a(CONST) and isinstance(item.value, str)):
                            fail((self.current_scope, node.lineno),
                                 Errors.MUST_BE_X, ['string literal'])
                        imp_name = item.value
                        self.current_scope.all_imports.append(imp_name)
                else:
                    fail((self.current_scope, node.lineno),
                         Errors.MUST_BE_X, ['A sequence of string literal'])
            if tail_lineno in self.type_comments:
                hint = self.type_comments[tail_lineno]
                mod = ast.parse(hint)
                ann = self.annotation_visitor.visit(mod.body[0])
                t = Type.from_annotation(ann, self.current_scope)
                if t:
                    left.symbol().set_type(t)
                else:
                    fail((self.current_scope, tail_lineno), Errors.UNKNOWN_TYPE_NAME, [ann])
            self.emit(MOVE(left, right), node)

    def visit_AugAssign(self, node):
        assert 0

    def visit_AnnAssign(self, node):
        ann = self.annotation_visitor.visit(node.annotation)
        src = None
        if node.value:
            src = self.visit(node.value)
        dst = self.visit(node.target)
        typ = Type.from_annotation(ann, self.current_scope)
        if not typ:
            fail((self.current_scope, node.lineno), Errors.UNKNOWN_TYPE_NAME, [ann])
        if dst.is_a(TEMP):
            if dst.symbol().typ.is_freezed():
                fail((self.current_scope, node.lineno), Errors.CONFLICT_TYPE_HINT)
            dst.symbol().set_type(typ)
        elif dst.is_a(ATTR):
            if (dst.exp.is_a(TEMP) and dst.head().name == env.self_name and
                    self.current_scope.is_method()):
                if isinstance(dst.attr, Symbol):
                    attr_sym = dst.attr
                else:
                    attr_sym = self.current_scope.parent.find_sym(dst.attr)
                if attr_sym.typ.is_freezed():
                    fail((self.current_scope, node.lineno), Errors.CONFLICT_TYPE_HINT)
                if self.current_scope.parent.is_module():
                    attr_sym.set_type(Type.port(typ))
                else:
                    attr_sym.set_type(typ)
                dst.attr = attr_sym
            else:
                fail((self.current_scope, node.lineno), Errors.UNSUPPORTED_ATTRIBUTE_TYPE_HINT)
        if src:
            self.emit(MOVE(dst, src), node)

    def visit_If(self, node):
        #
        #  if condition goto true_block else goto false_block
        #ifthen:
        #  ...
        #  goto ifexit
        #ifelse:
        #  ...
        #  goto ifexit
        #ifexit:

        if_head = self.current_block
        if_then = self._new_block(self.current_scope, 'ifthen')
        if_else_tmp = self._new_block(self.current_scope, 'ifelse')
        if_exit_tmp = self._new_block(self.current_scope)

        condition = self.visit(node.test)
        if not condition.is_a(RELOP):
            condition = RELOP('NotEq', condition, CONST(0))

        self.emit_to(if_head, CJUMP(condition, if_then, if_else_tmp), node)
        if_head.connect(if_then)
        if_head.connect(if_else_tmp)

        #if then block
        #if not self.nested_if:
        self.current_block = if_then
        for stm in node.body:
            self.visit(stm)
        if self._needJUMP(self.current_block):
            self.emit(JUMP(if_exit_tmp), node)
            self.current_block.connect(if_exit_tmp)
        #if not self.nested_if:
        #else:
        #    self.nested_if = False

        self.nested_if = False
        if node.orelse and isinstance(node.orelse[0], ast.If):
            self.nested_if = True

        #if else block
        if_else = self._new_block(self.current_scope, 'ifelse')
        self.current_scope.replace_block(if_else_tmp, if_else)
        self.current_block = if_else
        if node.orelse:
            if isinstance(node.orelse[0], ast.If):
                pass  # assert False
            for stm in node.orelse:
                self.visit(stm)
        if self._needJUMP(self.current_block):
            self.emit(JUMP(if_exit_tmp), node)
            self.current_block.connect(if_exit_tmp)

        #if_exit belongs to the outer level
        if_exit = self._new_block(self.current_scope)
        self.current_scope.replace_block(if_exit_tmp, if_exit)
        self.current_block = if_exit

    def visit_While(self, node):
        #
        #while:
        #   if condition then goto whilebody else goto whileelse
        #whilebody:
        #   ...
        #   goto whilebridge
        #whilebridge:
        #   goto while
        #whileelse:
        #   ...
        #   goto whileexit
        #whileexit:

        while_block = self._new_block(self.current_scope, 'while')
        body_block = self._new_block(self.current_scope, 'whilebody')
        loop_bridge_tmp_block = self._tmp_block(self.current_scope)
        else_tmp_block = self._tmp_block(self.current_scope)
        exit_tmp_block = self._tmp_block(self.current_scope)

        self.emit(JUMP(while_block), node)
        self.current_block.connect(while_block)

        # loop check part
        self.current_block = while_block
        condition = self.visit(node.test)
        if not condition.is_a(RELOP):
            condition = RELOP('NotEq', condition, CONST(0))
        cjump = CJUMP(condition, body_block, else_tmp_block)
        cjump.loop_branch = True
        self.emit(cjump, node)
        while_block.connect(body_block)
        while_block.connect(else_tmp_block)

        # body part
        self.current_block = body_block
        self.loop_bridge_blocks.append(loop_bridge_tmp_block)  # for 'continue'
        self.loop_end_blocks.append(exit_tmp_block)  # for 'break'
        for stm in node.body:
            self.visit(stm)
        if self._needJUMP(self.current_block):
            self.emit(JUMP(loop_bridge_tmp_block), node)
            self.current_block.connect(loop_bridge_tmp_block)

        # need loop bridge for branch merging
        if loop_bridge_tmp_block.preds:
            loop_bridge_block = self._new_block(self.current_scope, 'whilebridge')
            self.current_scope.replace_block(loop_bridge_tmp_block, loop_bridge_block)
            self.current_block = loop_bridge_block
            self.emit(JUMP(while_block, 'L'), node)
            loop_bridge_block.connect_loop(while_block)

        # else part
        else_block = self._new_block(self.current_scope, 'whileelse')
        self.current_scope.replace_block(else_tmp_block, else_block)
        self.current_block = else_block
        if node.orelse:
            for stm in node.orelse:
                self.visit(stm)
        if self._needJUMP(self.current_block):
            self.emit(JUMP(exit_tmp_block), node)
            self.current_block.connect(exit_tmp_block)

        self.loop_bridge_blocks.pop()
        self.loop_end_blocks.pop()

        exit_block = self._new_block(self.current_scope, 'whileexit')
        self.current_scope.replace_block(exit_tmp_block, exit_block)
        self.current_block = exit_block

    def visit_For(self, node):
        #  i = lo
        #loop_check
        #  if i < hi then goto start
        #            else goto end
        #body:
        #  stms...
        #  goto loop_continue
        #loop_continue
        #  i = i + step
        #  goto loop_check
        #end:
        def make_temp_if_needed(var, stms):
            if not var.is_a(CONST):
                temp_sym = self.current_scope.add_temp()
                stms += [MOVE(TEMP(temp_sym, Ctx.STORE), var)]
                var = TEMP(temp_sym, Ctx.LOAD)
            return var

        def is_iterator_func(ir):
            return it.is_a(SYSCALL) and it.sym.name in ('polyphony.unroll', 'polyphony.pipelined')

        var = self.visit(node.target)
        it = self.visit(node.iter)

        loop_synth_params = {}
        while is_iterator_func(it):
            assert len(it.args) >= 1
            _, seq = it.args[0]
            if it.sym.name == 'polyphony.unroll':
                if is_iterator_func(seq) and seq.sym.name in ('polyphony.unroll', 'polyphony.pipelined'):
                    fail((self.current_scope, node.lineno),
                         Errors.INCOMPATIBLE_PARAMETER_TYPE, [seq.sym.name, it.sym.name])
                if len(it.args) == 1:
                    if len(it.kwargs) == 0:
                        assert it.sym.typ.is_function()
                        scp = it.sym.typ.get_scope()
                        factor = scp.params[1].defval
                    elif len(it.kwargs) == 1 and 'factor' in it.kwargs:
                        factor = it.kwargs['factor']
                    else:
                        kwarg = list(it.kwargs.keys())[0]
                        fail((self.current_scope, node.lineno),
                             Errors.GOT_UNEXPECTED_KWARGS, [it.sym.name, kwarg])
                elif len(it.args) == 2:
                    _, factor = it.args[1]
                else:
                    fail((self.current_scope, node.lineno),
                         Errors.TAKES_TOOMANY_ARGS, [it.sym.name, '2', len(it.args)])
                loop_synth_params.update({'unroll':factor.value})
            elif it.sym.name == 'polyphony.pipelined':
                loop_synth_params.update({'scheduling':'pipeline'})
                if is_iterator_func(seq):
                    if seq.sym.name == 'polyphony.pipelined':
                        fail((self.current_scope, node.lineno),
                             Errors.INCOMPATIBLE_PARAMETER_TYPE, [seq.sym.name, it.sym.name])
                if len(it.args) == 1:
                    if len(it.kwargs) == 0:
                        assert it.sym.typ.is_function()
                        scp = it.sym.typ.get_scope()
                        ii = scp.params[1].defval
                    elif len(it.kwargs) == 1 and 'ii' in it.kwargs:
                        ii = it.kwargs['ii']
                    else:
                        kwarg = list(it.kwargs.keys())[0]
                        fail((self.current_scope, node.lineno),
                             Errors.GOT_UNEXPECTED_KWARGS, [it.sym.name, kwarg])
                elif len(it.args) == 2:
                    _, ii = it.args[1]
                else:
                    fail((self.current_scope, node.lineno),
                         Errors.TAKES_TOOMANY_ARGS, [it.sym.name, '2', len(it.args)])
                loop_synth_params.update({'ii':ii.value})
            it = seq

        # In case of range() loop
        if it.is_a(SYSCALL) and it.sym.name == 'range':
            init_parts = []
            if len(it.args) == 1:
                start = CONST(0)
                end = it.args[0][1]
                step = CONST(1)
            elif len(it.args) == 2:
                start = it.args[0][1]
                end = it.args[1][1]
                step = CONST(1)
            else:
                start = it.args[0][1]
                end = it.args[1][1]
                step = it.args[2][1]
            start = make_temp_if_needed(start, init_parts)
            end = make_temp_if_needed(end, init_parts)
            step = make_temp_if_needed(step, init_parts)
            counter = var.sym
            init_parts += [
                MOVE(TEMP(var.sym, Ctx.STORE), start)
            ]
            # negative step value
            #s_le_e = RELOP('LtE', start, end)
            #i_lt_e = RELOP('Lt', TEMP(var.sym, Ctx.LOAD), end)
            #s_gt_e = RELOP('Gt', start, end)
            #i_gt_e = RELOP('Gt', TEMP(var.sym, Ctx.LOAD), end)
            #cond0 = RELOP('And', s_le_e, i_lt_e)
            #cond1 = RELOP('And', s_gt_e, i_gt_e)
            #condition = RELOP('Or', cond0, cond1)
            condition = RELOP('Lt', TEMP(var.sym, Ctx.LOAD), end)
            continue_parts = [
                MOVE(TEMP(var.sym, Ctx.STORE),
                     BINOP('Add',
                           TEMP(var.sym, Ctx.LOAD),
                           step))
            ]
            self._build_for_loop_blocks(init_parts, condition, [], continue_parts, loop_synth_params, node)
        elif it.is_a([TEMP, ATTR]):
            start = CONST(0)
            end  = SYSCALL(builtin_symbols['len'], [('seq', it.clone())], {})
            counter_name = Symbol.unique_name('@counter')
            counter = self.current_scope.add_sym(counter_name)
            init_parts = [
                MOVE(TEMP(counter, Ctx.STORE),
                     start)
            ]
            condition = RELOP('Lt', TEMP(counter, Ctx.LOAD), end)
            body_parts = [
                MOVE(TEMP(var.sym, Ctx.STORE),
                     MREF(it.clone(),
                          TEMP(counter, Ctx.LOAD),
                          Ctx.LOAD))
            ]
            continue_parts = [
                MOVE(TEMP(counter, Ctx.STORE),
                     BINOP('Add',
                           TEMP(counter, Ctx.LOAD),
                           CONST(1)))
            ]
            self._build_for_loop_blocks(init_parts, condition, body_parts, continue_parts, loop_synth_params, node)
        elif it.is_a(ARRAY):
            unnamed_array = self.current_scope.add_temp('@unnamed')
            start = CONST(0)
            end  = SYSCALL(builtin_symbols['len'], [('seq', TEMP(unnamed_array, Ctx.LOAD))], {})
            counter_name = Symbol.unique_name('@counter')
            counter = self.current_scope.add_sym(counter_name)
            init_parts = [
                MOVE(TEMP(unnamed_array, Ctx.STORE),
                     it),
                MOVE(TEMP(counter, Ctx.STORE),
                     start)
            ]
            condition = RELOP('Lt', TEMP(counter, Ctx.LOAD), end)
            body_parts = [
                MOVE(TEMP(var.sym, Ctx.STORE),
                     MREF(TEMP(unnamed_array, Ctx.LOAD),
                          TEMP(counter, Ctx.LOAD),
                          Ctx.LOAD))
            ]
            continue_parts = [
                MOVE(TEMP(counter, Ctx.STORE),
                     BINOP('Add',
                           TEMP(counter, Ctx.LOAD),
                           CONST(1)))
            ]
            self._build_for_loop_blocks(init_parts, condition, body_parts, continue_parts, loop_synth_params, node)
        else:
            fail((self.current_scope, node.lineno),
                 Errors.UNSUPPORTED_SYNTAX, ['This type of for statement'])
        self.invisible_symbols.add(counter)

    def _build_for_loop_blocks(self, init_parts, condition, body_parts, continue_parts, loop_synth_params, node):
        exit_tmp_block = self._tmp_block(self.current_scope)

        old_loop_synth_params = self.current_loop_synth_params
        self.current_loop_synth_params = loop_synth_params
        loop_check_block = self._new_block(self.current_scope, 'fortest')
        body_block = self._new_block(self.current_scope, 'forbody')
        else_tmp_block = self._tmp_block(self.current_scope)
        continue_tmp_block = self._tmp_block(self.current_scope)

        # initialize part
        for code in init_parts:
            self.emit(code, node)
        self.emit(JUMP(loop_check_block), node)
        self.current_block.connect(loop_check_block)

        # loop check part
        self.current_block = loop_check_block

        cjump = CJUMP(condition, body_block, else_tmp_block)
        cjump.loop_branch = True
        self.emit(cjump, node)
        self.current_block.connect(body_block)
        self.current_block.connect(else_tmp_block)

        # body part
        self.current_block = body_block
        self.loop_bridge_blocks.append(continue_tmp_block)  # for 'continue'
        self.loop_end_blocks.append(exit_tmp_block)  # for 'break'
        for code in body_parts:
            self.emit(code, node)
        for stm in node.body:
            self.visit(stm)
        if self._needJUMP(self.current_block):
            self.emit(JUMP(continue_tmp_block), node)
            self.current_block.connect(continue_tmp_block)

        #continue part
        continue_block = self._new_block(self.current_scope, 'continue')
        self.current_scope.replace_block(continue_tmp_block, continue_block)
        self.current_block = continue_block
        for code in continue_parts:
            self.emit(code, node)
        self.emit(JUMP(loop_check_block, 'L'), node)
        continue_block.connect_loop(loop_check_block)

        #else part
        else_block = self._new_block(self.current_scope, 'forelse')
        self.current_scope.replace_block(else_tmp_block, else_block)
        self.current_block = else_block
        if node.orelse:
            for stm in node.orelse:
                self.visit(stm)
        if self._needJUMP(self.current_block):
            self.emit(JUMP(exit_tmp_block), node)
            self.current_block.connect(exit_tmp_block)

        self.loop_bridge_blocks.pop()
        self.loop_end_blocks.pop()

        exit_block = self._new_block(self.current_scope)
        self.current_scope.replace_block(exit_tmp_block, exit_block)
        self.current_block = exit_block
        self.current_loop_synth_params = old_loop_synth_params

    def visit_AyncFor(self, node):
        fail((self.current_scope, node.lineno), Errors.UNSUPPORTED_SYNTAX, ['async for statement'])

    def _is_empty_entry(self):
        return all([stm in self.current_param_stms for stm in self.current_scope.entry_block.stms])

    def visit_With(self, node):
        is_empty_entry = self.current_block is self.current_scope.entry_block and self._is_empty_entry()
        if not is_empty_entry:
            with_block = self._new_block(self.current_scope, 'with')
            self.emit(JUMP(with_block), node)
            self.current_block.connect(with_block)
            self.current_block = with_block
        # TODO: __enter__ and __exit__ calls
        old_with_blk_synth_params = None
        for item in node.items:
            expr, var = self.visit(item)
            if expr.is_a(CALL):
                if expr.func.symbol().typ.get_scope().name == 'polyphony.rule':
                    # merge nested params
                    old_with_blk_synth_params = self.current_with_blk_synth_params
                    self.current_with_blk_synth_params = self.current_with_blk_synth_params.copy()
                    self.current_with_blk_synth_params.update({k:v.value for k, v in expr.kwargs.items()})
                    if len(node.items) != 1:
                        assert False  # TODO: use fail()
                    if expr.args:
                        assert False  # TODO: use fail()
                    break
                elif var:
                    self.emit(MOVE(var, expr), node)
                else:
                    self.emit(EXPR(expr), node)
            else:
                raise NotImplementedError()
        self.current_block.synth_params.update(self.current_with_blk_synth_params)

        for body in node.body:
            self.visit(body)

        if old_with_blk_synth_params is not None:
            self.current_with_blk_synth_params = old_with_blk_synth_params

        if self._needJUMP(self.current_block):
            new_block = self._new_block(self.current_scope)
            self.emit(JUMP(new_block), node)
            self.current_block.connect(new_block)
            self.current_block = new_block

    def visit_withitem(self, node):
        expr = self.visit(node.context_expr)
        if node.optional_vars:
            var = self.visit(node.optional_vars)
            return expr, var
        else:
            return expr, None

    def visit_AsyncWith(self, node):
        fail((self.current_scope, node.lineno), Errors.UNSUPPORTED_SYNTAX, ['async with statement'])

    def visit_Raise(self, node):
        fail((self.current_scope, node.lineno), Errors.UNSUPPORTED_SYNTAX, ['raise statement'])

    def visit_Try(self, node):
        fail((self.current_scope, node.lineno), Errors.UNSUPPORTED_SYNTAX, ['try statement'])

    def visit_ExceptHandler(self, node):
        fail((self.current_scope, node.lineno), Errors.UNSUPPORTED_SYNTAX, ['except statement'])

    def visit_Assert(self, node):
        testexp = self.visit(node.test)
        self.emit(EXPR(SYSCALL(builtin_symbols['assert'], [('exp', testexp)], {})), node)

    def visit_Global(self, node):
        fail((self.current_scope, node.lineno), Errors.UNSUPPORTED_SYNTAX, ['global statement'])

    def visit_Nonlocal(self, node):
        fail((self.current_scope, node.lineno), Errors.UNSUPPORTED_SYNTAX, ['nonlocal statement'])

    def visit_Expr(self, node):
        exp = self.visit(node.value)
        if exp:
            self.emit(EXPR(exp), node)

    def visit_Pass(self, node):
        pass

    def visit_Break(self, node):
        if self.current_block.synth_params['scheduling'] == 'pipeline':
            fail((self.current_scope, node.lineno), Errors.RULE_BREAK_IN_PIPELINE_LOOP)
        end_block = self.loop_end_blocks[-1]
        self.emit(JUMP(end_block, 'B'), node)
        self.current_block.connect(end_block)

    def visit_Continue(self, node):
        if self.current_block.synth_params['scheduling'] == 'pipeline':
            fail((self.current_scope, node.lineno), Errors.RULE_CONTINUE_IN_PIPELINE_LOOP)
        bridge_block = self.loop_bridge_blocks[-1]
        self.emit(JUMP(bridge_block), node)
        self.current_block.connect(bridge_block)

    #--------------------------------------------------------------------------
    def visit_BoolOp(self, node):
        values = list(node.values)
        values.reverse()
        tail = self.visit(values[0])
        for val in values[1:]:
            head = self.visit(val)
            tail = RELOP(op2str(node.op), head, tail)
        return tail

    def visit_BinOp(self, node):
        left = self.visit(node.left)
        right = self.visit(node.right)
        return BINOP(op2str(node.op), left, right)

    def visit_UnaryOp(self, node):
        exp = self.visit(node.operand)
        unop = UNOP(op2str(node.op), exp)
        if exp.is_a(CONST):
            v = eval_unop(unop)
            if v is None:
                fail((self.current_scope, node.lineno), Errors.UNSUPPORTED_OPERATOR, [unop.op])
            return CONST(v)
        return unop

    def visit_Lambda(self, node):
        fail((self.current_scope, node.lineno), Errors.UNSUPPORTED_SYNTAX, ['lambda'])

    def visit_IfExp(self, node):
        condition = self.visit(node.test)
        then_exp = self.visit(node.body)
        else_exp = self.visit(node.orelse)
        return CONDOP(condition, then_exp, else_exp)

    def visit_Dict(self, node):
        fail((self.current_scope, node.lineno), Errors.UNSUPPORTED_SYNTAX, ['dict'])

    def visit_Set(self, node):
        fail((self.current_scope, node.lineno), Errors.UNSUPPORTED_SYNTAX, ['set'])

    def visit_ListComp(self, node):
        fail((self.current_scope, node.lineno), Errors.UNSUPPORTED_SYNTAX, ['list comprehension'])

    def visit_SetComp(self, node):
        fail((self.current_scope, node.lineno), Errors.UNSUPPORTED_SYNTAX, ['set comprehension'])

    def visit_DictComp(self, node):
        fail((self.current_scope, node.lineno), Errors.UNSUPPORTED_SYNTAX, ['dict comprehension'])

    def visit_GeneratorExp(self, node):
        fail((self.current_scope, node.lineno), Errors.UNSUPPORTED_SYNTAX, ['generator expression'])

    def visit_Yield(self, node):
        fail((self.current_scope, node.lineno), Errors.UNSUPPORTED_SYNTAX, ['yield'])

    def visit_YieldFrom(self, node):
        fail((self.current_scope, node.lineno), Errors.UNSUPPORTED_SYNTAX, ['yield from'])

    def visit_Compare(self, node):
        assert len(node.ops) == 1
        left = self.visit(node.left)
        op = node.ops[0]
        right = self.visit(node.comparators[0])
        return RELOP(op2str(op), left, right)

    def visit_Call(self, node):
        #      pass by name
        #if isinstance(node.func, ast.Name):
        #    if node.func.id in builtin_type_names:
        #        pass
        func = self.visit(node.func)
        kwargs = {}
        if node.keywords:
            for kw in node.keywords:
                kwargs[kw.arg] = self.visit(kw.value)
        args = [(None, self.visit(arg)) for arg in node.args]

        if getattr(node, 'starargs', None) and node.starargs:
            fail((self.current_scope, node.lineno), Errors.UNSUPPORTED_SYNTAX, ['star args'])
        #stararg = self.visit(node.starargs)

        if func.is_a(TEMP):
            if func.symbol().typ.is_class():
                return NEW(func.symbol(), args, kwargs)
            sym = self.current_scope.find_sym(func.symbol().name)
            func_scope = sym.typ.get_scope() if sym.typ.has_scope() else None
            #assert func_scope
            if not func_scope:
                if func.symbol().name in dir(python_builtins):
                    raise NameError("The name \'{}\' is reserved as the name of the built-in function.".
                                    format(node.func.id))
            else:
                if func.symbol().name in builtin_symbols:
                    return SYSCALL(builtin_symbols[func.symbol().name], args, kwargs)
                elif func_scope.name in builtin_symbols:
                    return SYSCALL(builtin_symbols[func_scope.name], args, kwargs)
        elif func.is_a(ATTR) and func.exp.is_a([TEMP, ATTR]):
            if isinstance(func.attr, Symbol):
                if (func.attr.typ.is_function()
                        and func.attr.typ.get_scope().name in builtin_symbols):
                    builtin_sym = builtin_symbols[func.attr.typ.get_scope().name]
                    return SYSCALL(builtin_sym, args, kwargs)
                elif func.attr.typ.is_class():
                    return NEW(func.attr, args, kwargs)
            else:
                scope_sym = func.tail()
                if isinstance(scope_sym, Symbol):
                    if scope_sym.typ.is_containable():
                        receiver = scope_sym.typ.get_scope()
                        attr_sym = receiver.find_sym(func.attr)
                        if attr_sym.typ.is_class():
                            return NEW(attr_sym, args, kwargs)
        return CALL(func, args, kwargs)

    def visit_Num(self, node):
        return CONST(node.n)

    def visit_Str(self, node):
        return CONST(node.s)

    def visit_Bytes(self, node):
        fail((self.current_scope, node.lineno), Errors.UNSUPPORTED_SYNTAX, ['bytes'])

    def visit_Ellipsis(self, node):
        fail((self.current_scope, node.lineno), Errors.UNSUPPORTED_SYNTAX, ['ellipsis'])

    #     | Attribute(expr value, identifier attr, expr_context ctx)
    def visit_Attribute(self, node):
        ctx = self._nodectx2irctx(node)
        value = self.visit(node.value)
        if (value.is_a([TEMP, ATTR]) and isinstance(value.symbol(), Symbol) and
                value.symbol().typ.has_scope()):
            scope = value.symbol().typ.get_scope()
            attr = None
            if scope:
                if ctx == Ctx.STORE:
                    if scope.has_sym(node.attr):
                        attr = scope.find_sym(node.attr)
                    else:
                        attr = scope.add_sym(node.attr)
                else:
                    attr = scope.find_sym(node.attr)
            if not attr:
                attr = node.attr
        else:
            attr = node.attr
        irattr = ATTR(value, attr, ctx)

        if irattr.head() and irattr.head().name == env.self_name and isinstance(attr, str):
            scope = irattr.head().typ.get_scope()
            if ctx & Ctx.STORE:
                scope.gen_sym(attr)
        return irattr

    #     | Subscript(expr value, slice slice, expr_context ctx)
    def visit_Subscript(self, node):
        v = self.visit(node.value)
        ctx = self._nodectx2irctx(node)
        v.ctx = ctx
        if isinstance(node.slice, (ast.Slice, ast.ExtSlice)):
            fail((self.current_scope, node.lineno), Errors.UNSUPPORTED_SYNTAX, ['slice'])
        s = self.visit(node.slice)
        return MREF(v, s, ctx)

    #     | Starred(expr value, expr_context ctx)
    def visit_Starred(self, node):
        fail((self.current_scope, node.lineno), Errors.UNSUPPORTED_SYNTAX, ['starred'])

    #     | Name(identifier id, expr_context ctx)
    def visit_Name(self, node):
        # for Python 3.3 or older
        if node.id == 'True':
            return CONST(True)
        elif node.id == 'False':
            return CONST(False)
        elif node.id == 'None':
            return CONST(None)

        ctx = self._nodectx2irctx(node)
        sym = self.current_scope.find_sym(node.id)
        if not sym:
            parent_scope = self.current_scope.find_parent_scope(node.id)
            if parent_scope:
                scope_sym = parent_scope.find_sym(node.id)
                return TEMP(scope_sym, self._nodectx2irctx(node))

        if ctx == Ctx.LOAD:
            if sym is None:
                fail((self.current_scope, node.lineno), Errors.UNDEFINED_NAME, [node.id])
        else:
            if sym is None or sym.scope is not self.current_scope:
                sym = self.current_scope.add_sym(node.id)
                if self.current_scope.is_namespace() or self.current_scope.is_class():
                    sym.add_tag('static')
        if sym in self.invisible_symbols:
            if ctx == Ctx.LOAD:
                fail((self.current_scope, node.lineno), Errors.NAME_SCOPE_RESTRICTION, [node.id])
            else:
                self.invisible_symbols.remove(sym)
        assert sym is not None
        return TEMP(sym, ctx)

    #     | List(expr* elts, expr_context ctx)
    def visit_List(self, node):
        items = []
        for elt in node.elts:
            item = self.visit(elt)
            items.append(item)
        return ARRAY(items)

    #     | Tuple(expr* elts, expr_context ctx)
    def visit_Tuple(self, node):
        items = []
        for elt in node.elts:
            item = self.visit(elt)
            items.append(item)
        return ARRAY(items, is_mutable=False)

    def visit_NameConstant(self, node):
        # for Python 3.4
        if node.value is True:
            return CONST(True)
        elif node.value is False:
            return CONST(False)
        elif node.value is None:
            return CONST(None)

    def visit_Slice(self, node):
        assert False

    def visit_ExtSlice(self, node):
        assert False

    def visit_Index(self, node):
        return self.visit(node.value)

    def visit_Print(self, node):
        fail((self.current_scope, node.lineno), Errors.UNSUPPORTED_SYNTAX, ['print statement'])


class AnnotationVisitor(ast.NodeVisitor):
    def __init__(self, parent_visitor):
        self.parent_visitor = parent_visitor

    def visit_Expr(self, node):
        return self.visit(node.value)

    def visit_Subscript(self, node):
        v = self.visit(node.value)
        s = self.visit(node.slice)
        return (v, s)

    def visit_Index(self, node):
        return self.visit(node.value)

    def visit_Name(self, node):
        return node.id

    def visit_NameConstant(self, node):
        # for Python 3.4
        if node.value is True:
            return 'True'
        elif node.value is False:
            return 'False'
        elif node.value is None:
            return 'None'

    def visit_Ellipsis(self, node):
        return '...'

    def visit_Attribute(self, node):
        value = self.visit(node.value)
        attr = node.attr
        return '{}.{}'.format(value, attr)

    def visit_Call(self, node):
        func = self.visit(node.func)
        args = list(map(self.visit, node.args))
        return (func, args)

    def visit_Tuple(self, node):
        items = []
        for elt in node.elts:
            item = self.visit(elt)
            items.append(item)
        return tuple(items)

    def visit_Num(self, node):
        return node.n

    def visit_Str(self, node):
        return node.s


class DecoratorVisitor(AnnotationVisitor):
    def visit_Call(self, node):
        func = self.visit(node.func)
        args = list(map(self.visit, node.args))
        kwargs = {}
        for kw in node.keywords:
            kwargs[kw.arg] = self.visit(kw.value)
        return (func, args, kwargs)


class PureScopeVisitor(ast.NodeVisitor):
    def __init__(self, scope, type_comments):
        self.scope = scope
        self.scope.local_type_hints = {}
        self.type_comments = type_comments
        self.annotation_visitor = AnnotationVisitor(self)

    def _add_local_type_hint(self, local_type_hints, name, typ):
        if '.' not in name:
            local_type_hints[name] = typ
        else:
            first_dot = name.find('.')
            receiver = name[:first_dot]
            rest = name[first_dot + 1:]
            if receiver not in local_type_hints:
                local_type_hints[receiver] = {}
            sub_dict = local_type_hints[receiver]
            self._add_local_type_hint(sub_dict, rest, typ)

    def visit_Name(self, node):
        return node.id

    def visit_Attribute(self, node):
        value = self.visit(node.value)
        attr = node.attr
        return '{}.{}'.format(value, attr)

    def visit_Assign(self, node):
        tail_lineno = _get_tail_lineno(node.value)
        # When there are multiple targets, e.g. x = y = 1
        for target in node.targets:
            left = self.visit(target)
            if not left:
                continue
            if tail_lineno in self.type_comments:
                hint = self.type_comments[tail_lineno]
                mod = ast.parse(hint)
                ann = self.annotation_visitor.visit(mod.body[0])
                typ = Type.from_annotation(ann, self.scope)
                if typ:
                    self._add_local_type_hint(self.scope.local_type_hints, left, typ)
                else:
                    fail((self.scope, tail_lineno), Errors.UNKNOWN_TYPE_NAME, [ann])

    def visit_AnnAssign(self, node):
        ann = self.annotation_visitor.visit(node.annotation)
        left = self.visit(node.target)
        typ = Type.from_annotation(ann, self.scope)
        if not typ:
            fail((self.scope, node.lineno), Errors.UNKNOWN_TYPE_NAME, [ann])
        if left:
            self._add_local_type_hint(self.scope.local_type_hints, left, typ)

    def visit_Call(self, node):
        func = self.visit(node.func)
        if func:
            sym = self.scope.find_sym(func)
            if sym and sym.typ.has_scope():
                sym_scope = sym.typ.get_scope()
                if sym_scope.is_typeclass():
                    t = Type.from_typeclass(sym_scope)
                else:
                    t = Type.object(sym_scope)
                t.freeze()
                if t:
                    self._add_local_type_hint(self.scope.local_type_hints, func, t)
                    return func

    def visit_Global(self, node):
        fail((self.scope, node.lineno), Errors.UNSUPPORTED_SYNTAX, ['global statement'])

    def visit_FunctionDef(self, node):
        if self.scope.orig_name != node.name:
            fail((self.scope, node.lineno), Errors.UNSUPPORTED_SYNTAX, ['nested function in @pure function'])
        else:
            self.generic_visit(node)

    def visit_ClassDef(self, node):
        fail((self.scope, node.lineno), Errors.UNSUPPORTED_SYNTAX, ['nested class in @pure function'])


def scope_tree_str(scp, name, typ_name, indent):
    s = '{}{} : {}\n'.format(indent, name, typ_name)
    for sym in sorted(scp.symbols.values()):
        if sym.typ.is_containable():
            s += scope_tree_str(sym.typ.get_scope(), sym.name, sym.typ.name, indent + '  ')
        else:
            s += '{}{} : {}\n'.format(indent + '  ', sym.name, sym.typ)
    return s


def _get_tail_lineno(node):
    def _get_tail_lineno_r(node, maxlineno):
        if not hasattr(node, 'lineno'):
            return
        if node.lineno > maxlineno[0]:
            maxlineno[0] = node.lineno
        for field in ast.iter_child_nodes(node):
            if isinstance(field, list):
                for fld in field:
                    _get_tail_lineno_r(fld, maxlineno)
            else:
                _get_tail_lineno_r(field, maxlineno)
    maxlineno = [0]
    _get_tail_lineno_r(node, maxlineno)
    return maxlineno[0]


class IRTranslator(object):
    def __init__(self):
        pass

    def _extract_type_comment(self, source):
        lines = source.split('\n')
        type_comments = {}
        for i, line in enumerate(lines):
            idx = line.find('#')
            if idx == -1:
                continue
            comment = line[idx:]
            idx = comment.find('type:')
            if idx == -1:
                continue
            type_hint = comment[idx + len('type:'):].strip()
            type_comments[i + 1] = type_hint
        return type_comments

    def translate(self, source, lib_name, top=None):
        tree = ast.parse(source)
        if lib_name:
            if lib_name == '__builtin__':
                top_scope = Scope.create_namespace(None, lib_name, {'lib'})
            elif lib_name == 'polyphony':
                top_scope = Scope.create_namespace(None, lib_name, {'lib'})
                for sym in builtin_symbols.values():
                    top_scope.import_sym(sym)
            else:
                lib_root = env.scopes['polyphony']
                top_scope = Scope.create_namespace(lib_root, lib_name, {'lib'})
                sym = lib_root.add_sym(lib_name, typ=Type.namespace(top_scope))
        else:
            if top:
                top_scope = top
            else:
                top_scope = Scope.global_scope()
            ImportVisitor(top_scope).visit(tree)
            logger.debug(scope_tree_str(top_scope, top_scope.name, 'namespace', ''))
            logger.debug('ignore packages')
            logger.debug(ignore_packages)
        type_comments = self._extract_type_comment(source)
        ScopeVisitor(top_scope).visit(tree)
        CompareTransformer().visit(tree)
        AugAssignTransformer().visit(tree)
        CodeVisitor(top_scope, type_comments).visit(tree)
        #print(scope_tree_str(top_scope, top_scope.name, 'namespace', ''))