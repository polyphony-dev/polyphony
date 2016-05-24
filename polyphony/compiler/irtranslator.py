import os
import ast
import inspect
import sys
import re
import codeop
import pdb
from .ir import *
from .block import Block
from .scope import Scope, FunctionParam
from .symbol import Symbol, function_name
from .type import Type
from .env import env
from .common import error_info
from .builtin import builtin_names
from logging import getLogger
logger = getLogger(__name__)

attr_map = {}

class FunctionVisitor(ast.NodeVisitor):
    def __init__(self):
        self.current_scope = Scope.create(None, '@top', [])

    def visit_FunctionDef(self, node):
        #arguments = (arg* args, identifier? vararg, expr? varargannotation,
        #            arg* kwonlyargs, identifier? kwarg,
        #             expr? kwargannotation, expr* defaults,
        #             expr* kw_defaults)
        #arg = (identifier arg, expr? annotation)

        outer_scope = self.current_scope

        attributes = []
        for deco in node.decorator_list:
            if deco.id in ['testbench', 'top', 'classmethod']:
                attributes = []
                attributes.append(deco.id)
                break
        if outer_scope.is_class() and 'classmethod' not in attributes:
            attributes.append('method')
        self.current_scope = Scope.create(outer_scope, node.name, attributes)

        for arg in node.args.args:
            param_in = self.current_scope.add_sym(Symbol.param_prefix+'_'+arg.arg)
            param_in.typ = Type.from_annotation(arg.annotation)
            param_copy = self.current_scope.add_sym(arg.arg)
            param_copy.typ = param_in.typ
            self.current_scope.add_param(param_in, param_copy, None)
        if self.current_scope.is_method():
            if not self.current_scope.params or self.current_scope.params[0].sym.name != Symbol.param_prefix+'_'+'self':
                print(error_info(node.lineno))
                raise RuntimeError("Class method must have a 'self' parameter.")
            first_param = self.current_scope.params[0]
            first_param.copy.typ = first_param.sym.typ = Type.object(None, outer_scope)

        for stm in node.body:
            self.visit(stm)
        self.current_scope = outer_scope

    def visit_ClassDef(self, node):
        outer_scope = self.current_scope
        self.current_scope = Scope.create(outer_scope, node.name, ['class'])
        for stm in node.body:
            self.visit(stm)

        self.current_scope = outer_scope

class CompareTransformer(ast.NodeTransformer):
    '''Transform 'v0 op v1 op v2' to 'v0 op v1 and v1 op v2' '''
    def visit_Compare(self, node):
        if len(node.ops) > 1:
            compares = []
            compares.append(ast.Compare(left=node.left, ops=node.ops[0:1], comparators=node.comparators[0:1]))
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
        binop = ast.BinOp(op = node.op, left = lhs, right = node.value)
        assign = ast.Assign(targets = [node.target], value = binop)
        return ast.copy_location(assign, node)

class AttributeVisitor(ast.NodeVisitor):
    def visit_Attribute(self, node):
        attr = attr_map[node]

class Visitor(ast.NodeVisitor):
    def __init__(self):
        self.import_list = {}
        self.importfrom_list = {}
        self.global_scope = env.scopes['@top']
        self.current_scope = self.global_scope
        self.current_scope.begin_block_group('@top')

        self.current_block = Block.create()
        self.current_scope.append_block(self.current_block)
        self.function_exit = None

        self.loop_bridge_blocks = []
        self.loop_end_blocks = []

        self.current_loop_info = self.current_scope.create_loop_info(self.current_block)
        self.nested_if = False
        self.last_node = None

    def result(self):
        return self.global_scope

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
        if not block.stms:
            return True
        last = block.stms[-1]
        return not last.is_a(JUMP) and \
            not (last.is_a(MOVE) and last.dst.is_a(TEMP) and last.dst.sym.is_return())
        
    #-------------------------------------------------------------------------
    
    def visit_Import(self, node):
        pass

    
    def visit_ImportFrom(self, node):
        pass


    #-------------------------------------------------------------------------

    def _enter_scope(self, name):
        outer_scope = self.current_scope
        self.current_scope = env.scopes[outer_scope.name + '.' + name]
        self.current_scope.begin_block_group('top')

        last_block = self.current_block
        new_block = Block.create()
        self.current_scope.append_block(new_block)
        self.current_block = new_block
        prev_loop_info = self.current_loop_info
        self.current_loop_info = self.current_scope.create_loop_info(self.current_block)

        outer_scope.add_sym(name)

        return (outer_scope, last_block, prev_loop_info)

    def _leave_scope(self, outer_scope, last_block, prev_loop_info):
        self.current_scope.end_block_group()
        self.current_scope = outer_scope
        self.current_block = last_block
        self.current_loop_info = prev_loop_info

    def visit_FunctionDef(self, node):
        context = self._enter_scope(node.name)

        outer_function_exit = self.function_exit
        self.function_exit = Block.create('exit')

        params = self.current_scope.params
        skip = len(node.args.args) - len(node.args.defaults)
        for idx, param in enumerate(params[:skip]):
            self.emit(MOVE(TEMP(param.copy, Ctx.STORE), TEMP(param.sym, Ctx.LOAD)), node)

        for idx, (param, defval) in enumerate(zip(params[skip:], node.args.defaults)):
            if Type.is_list(param.sym.typ):
                print(self._err_info(node))
                raise RuntimeError("cannot set the default value to the list type parameter.")
            d = self.visit(defval)
            params[skip+idx] = FunctionParam(param.sym, param.copy, d)
            self.emit(MOVE(TEMP(param.copy, Ctx.STORE), TEMP(param.sym, Ctx.LOAD)), node)

        for stm in node.body:
            self.visit(stm)

        #self.function_exit.branch_tags = []
        sym = self.current_scope.gen_sym(Symbol.return_prefix)
        self.emit_to(self.function_exit, RET(TEMP(sym, Ctx.LOAD)), self.last_node)
        self.current_scope.append_block(self.function_exit)
        self.function_exit = outer_function_exit

        self._leave_scope(*context)


    def visit_ClassDef(self, node):
        context = self._enter_scope(node.name)
        for body in node.body:
            self.visit(body)
        logger.debug(node.name)

        self._leave_scope(*context)

    def visit_Return(self, node):
        #TODO multiple return value
        sym = self.current_scope.gen_sym(Symbol.return_prefix)
        ret = TEMP(sym, Ctx.STORE)
        if node.value:
            self.emit(MOVE(ret, self.visit(node.value)), node)
        self.emit(JUMP(self.function_exit, 'E'), node)

        self.current_loop_info.append_return(self.current_block)
        self.current_block.connect(self.function_exit)

    
    def visit_Delete(self, node):
        print(self._err_info(node))
        raise RuntimeError("def statement is not supported.")

    
    def visit_Assign(self, node):
        right = self.visit(node.value)
        for target in node.targets:
            self.emit(MOVE(self.visit(target), right), node)

    
    def visit_AugAssign(self, node):
        assert 0

     
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
        if_then = Block.create('ifthen')
        if_else = Block.create('ifelse')
        if_exit = Block.create()

        condition = self.visit(node.test)
        if not condition.is_a(RELOP):
            condition = RELOP('NotEq', condition, CONST(0))

        self.emit_to(if_head, CJUMP(condition, if_then, if_else), node)
        if_head.connect_branch(if_then, True)
        if_head.connect_branch(if_else, False)
        
        #if then block
        #if not self.nested_if:
        self.current_scope.begin_block_group('ifthen')
        self.current_scope.append_block(if_then)
        self.current_block = if_then
        for stm in node.body:
            self.visit(stm)
        if self._needJUMP(self.current_block):
            self.emit(JUMP(if_exit), node)
            self.current_block.connect(if_exit)
        #if not self.nested_if:
        self.current_scope.end_block_group()
        #else:
        #    self.nested_if = False

        self.nested_if = False
        if node.orelse and isinstance(node.orelse[0], ast.If):
            self.nested_if = True

        #if else block
        self.current_scope.begin_block_group('ifelse')
        self.current_scope.append_block(if_else)
        self.current_block = if_else
        if node.orelse:
            if isinstance(node.orelse[0], ast.If):
                pass#assert False
            for stm in node.orelse:
                self.visit(stm)
        if self._needJUMP(self.current_block):
            self.emit(JUMP(if_exit), node)
            self.current_block.connect(if_exit)
        self.current_scope.end_block_group()
            
        if_exit.merge_branch(if_head)
        #if_exit belongs to the outer level
        self.current_scope.append_block(if_exit)
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

        while_block = Block.create('while')
        body_block = Block.create('whilebody')
        loop_bridge_block = Block.create('whilebridge')
        else_block = Block.create('whileelse')
        exit_block = Block.create('whileexit')


        self.emit(JUMP(while_block), node)
        self.current_block.connect(while_block)

        prev_loop_info = self.current_loop_info
        self.current_loop_info = self.current_scope.create_loop_info(while_block)

        #loop check part
        self.current_scope.append_block(while_block)
        self.current_block = while_block
        condition = self.visit(node.test)
        if not condition.is_a(RELOP):
            condition = RELOP('NotEq', condition, CONST(0))
        cjump = CJUMP(condition, body_block, else_block)
        cjump.loop_branch = True
        self.emit(cjump, node)
        while_block.connect_branch(body_block, True)
        while_block.connect_branch(else_block, False)

        #body part
        self.current_scope.begin_block_group('whilebody')
        self.current_scope.append_block(body_block)
        self.current_block = body_block
        self.loop_bridge_blocks.append(loop_bridge_block) #for 'continue'
        self.loop_end_blocks.append(exit_block) #for 'break'
        for stm in node.body:
            self.visit(stm)
        if self._needJUMP(self.current_block):
            self.emit(JUMP(loop_bridge_block, 'C'), node)
            self.current_block.connect(loop_bridge_block)
        self.current_scope.end_block_group()

        # need loop bridge for branch merging
        self.current_scope.begin_block_group('bridge')
        self.current_scope.append_block(loop_bridge_block)
        self.current_block = loop_bridge_block
        self.emit(JUMP(while_block, 'L'), node)
        loop_bridge_block.connect_loop(while_block)
        self.current_scope.end_block_group()

        #else part
        self.current_scope.begin_block_group('whileelse')
        self.current_scope.append_block(else_block)
        self.current_block = else_block
        if node.orelse:
            for stm in node.orelse:
                self.visit(stm)
        if self._needJUMP(self.current_block):
            self.emit(JUMP(exit_block), node)
            self.current_block.connect(exit_block)
        self.current_scope.end_block_group()

        self.current_loop_info.exit = else_block
        #self.current_scope.append_loop_info(self.current_loop_info)
        self.current_loop_info = prev_loop_info
        self.loop_bridge_blocks.pop()
        self.loop_end_blocks.pop()

        exit_block.merge_branch(while_block)
        self.current_scope.append_block(exit_block)
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

        var = self.visit(node.target)
        it = self.visit(node.iter)

        #In case of range() loop
        if it.is_a(SYSCALL) and it.name == 'range':
            if len(it.args) == 1:
                start = CONST(0)
                end = it.args[0]
                step = CONST(1)
            elif len(it.args) == 2:
                start = it.args[0]
                end = it.args[1]
                step = CONST(1)
            else:
                start = it.args[0]
                end = it.args[1]
                step = it.args[2]

            init_parts = [
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
                MOVE(TEMP(var.sym, Ctx.STORE), BINOP('Add', TEMP(var.sym, Ctx.LOAD), step))
            ]
            self._build_for_loop_blocks(init_parts, condition, [], continue_parts, node)
        elif it.is_a(TEMP):
            start = CONST(0)
            end  = SYSCALL('len', [(TEMP(it.sym, Ctx.LOAD))])
            counter = self.current_scope.add_temp('@counter')
            init_parts = [
                MOVE(TEMP(counter, Ctx.STORE),
                     start)
            ]
            condition = RELOP('Lt', TEMP(counter, Ctx.LOAD), end)
            body_parts = [
                MOVE(TEMP(var.sym, Ctx.STORE),
                     MREF(TEMP(it.sym, Ctx.LOAD), TEMP(counter, Ctx.LOAD), Ctx.LOAD))
            ]
            continue_parts = [
                MOVE(TEMP(counter, Ctx.STORE),
                     BINOP('Add', TEMP(counter, Ctx.LOAD), CONST(1)))
            ]
            self._build_for_loop_blocks(init_parts, condition, body_parts, continue_parts, node)
        elif it.is_a(ARRAY):
            unnamed_array = self.current_scope.add_temp('@unnamed')
            start = CONST(0)
            end  = SYSCALL('len', [(TEMP(unnamed_array, Ctx.LOAD))])
            counter = self.current_scope.add_temp('@counter')
            init_parts = [
                MOVE(TEMP(unnamed_array, Ctx.STORE),
                     it),
                MOVE(TEMP(counter, Ctx.STORE),
                     start)
            ]
            condition = RELOP('Lt', TEMP(counter, Ctx.LOAD), end)
            body_parts = [
                MOVE(TEMP(var.sym, Ctx.STORE),
                     MREF(TEMP(unnamed_array, Ctx.LOAD), TEMP(counter, Ctx.LOAD), Ctx.LOAD))
            ]
            continue_parts = [
                MOVE(TEMP(counter, Ctx.STORE),
                     BINOP('Add', TEMP(counter, Ctx.LOAD), CONST(1)))
            ]
            self._build_for_loop_blocks(init_parts, condition, body_parts, continue_parts, node)
        else:
            print(self._err_info(node))
            raise RuntimeError("unsupported for-loop")

    def _build_for_loop_blocks(self, init_parts, condition, body_parts, continue_parts, node):
        loop_check_block = Block.create('fortest')
        body_block = Block.create('forbody')
        else_block = Block.create('forelse')
        continue_block = Block.create('continue')
        exit_block = Block.create()

        #initialize part
        for code in init_parts:
            self.emit(code, node)
        self.emit(JUMP(loop_check_block), node)
        self.current_block.connect(loop_check_block)

        prev_loop_info = self.current_loop_info
        self.current_loop_info = self.current_scope.create_loop_info(loop_check_block)
        #loop check part
        self.current_scope.append_block(loop_check_block)
        self.current_block = loop_check_block

        cjump = CJUMP(condition, body_block, else_block)
        cjump.loop_branch = True
        self.emit(cjump, node)
        self.current_block.connect_branch(body_block, True)
        self.current_block.connect_branch(else_block, False)

        #body part
        self.current_scope.begin_block_group('forbody')
        self.current_scope.append_block(body_block)
        self.current_block = body_block
        self.loop_bridge_blocks.append(continue_block) #for 'continue'
        self.loop_end_blocks.append(exit_block) #for 'break'
        for code in body_parts:
            self.emit(code, node)
        for stm in node.body:
            self.visit(stm)
        if self._needJUMP(self.current_block):
            self.emit(JUMP(continue_block, 'C'), node)
            self.current_block.connect(continue_block)
        self.current_scope.end_block_group()

        #continue part
        self.current_scope.begin_block_group('bridge')
        self.current_scope.append_block(continue_block)
        self.current_block = continue_block
        for code in continue_parts:
            self.emit(code, node)
        self.emit(JUMP(loop_check_block, 'L'), node)
        continue_block.connect_loop(loop_check_block)
        self.current_scope.end_block_group()

        #else part
        self.current_scope.begin_block_group('forelse')
        self.current_scope.append_block(else_block)
        self.current_block = else_block
        if node.orelse:
            for stm in node.orelse:
                self.visit(stm)
        if self._needJUMP(self.current_block):
            self.emit(JUMP(exit_block), node)
            self.current_block.connect(exit_block)
        self.current_scope.end_block_group()

        self.current_loop_info.exit = else_block
        #self.current_scope.append_loop_info(self.current_loop_info)
        self.current_loop_info = prev_loop_info
        self.loop_bridge_blocks.pop()
        self.loop_end_blocks.pop()

        exit_block.merge_branch(loop_check_block)
        self.current_scope.append_block(exit_block)
        self.current_block = exit_block


    def visit_Assert(self, node):
        testexp = self.visit(node.test)
        self.emit(EXPR(SYSCALL('assert', [testexp])), node)

    #--------------------------------------------------------------------------
    
    def visit_Global(self, node):
        print(self._err_info(node))
        raise NotImplementedError('global statement is not supported')

    
    def visit_Nonlocal(self, node):
        print(self._err_info(node))
        raise NotImplementedError('nonlocal statement is not supported')

    
    def visit_Expr(self, node):
        exp = self.visit(node.value)
        if exp:
            self.emit(EXPR(exp), node)


    def visit_Pass(self, node):
        pass
    
    def visit_Break(self, node):
        end_block = self.loop_end_blocks[-1]
        self.emit(JUMP(end_block, 'B'), node)
        self.current_block.connect_break(end_block)
        self.current_loop_info.append_break(self.current_block)

    
    def visit_Continue(self, node):
        bridge_block = self.loop_bridge_blocks[-1]
        self.emit(JUMP(bridge_block, 'C'), node)
        self.current_block.connect_continue(bridge_block)

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
        return UNOP(op2str(node.op), exp)

    
    def visit_Lambda(self, node):
        print(self._err_info(node))
        raise NotImplementedError('lambda is not supported')

    def visit_IfExp(self, node):
        print(self._err_info(node))
        raise NotImplementedError('if exp is not supported')

    def visit_Dict(self, node):
        print(self._err_info(node))
        raise NotImplementedError('dict is not supported')

    def visit_Set(self, node):
        print(self._err_info(node))
        raise NotImplementedError('set is not supported')

    def visit_ListComp(self, node):
        print(self._err_info(node))
        raise NotImplementedError('list comprehension is not supported')

    def visit_SetComp(self, node):
        print(self._err_info(node))
        raise NotImplementedError('set comprehension is not supported')

    def visit_DictComp(self, node):
        print(self._err_info(node))
        raise NotImplementedError('dict comprehension is not supported')
    
    def visit_GeneratorExp(self, node):
        print(self._err_info(node))
        raise NotImplementedError('generator exp is not supported')
    
    def visit_Yield(self, node):
        print(self._err_info(node))
        raise NotImplementedError('yield is not supported')
    
    def visit_YieldFrom(self, node):
        print(self._err_info(node))
        raise NotImplementedError('yield from is not supported')

    def visit_Compare(self, node):
        assert len(node.ops) == 1
        left = self.visit(node.left)
        op = node.ops[0]
        right = self.visit(node.comparators[0])
        return RELOP(op2str(op), left, right)

    def visit_Call(self, node):
        #      pass by name
        func = self.visit(node.func)
        args = list(map(self.visit, node.args))
        if func.is_a(TEMP):
            func_name = function_name(func.sym)
            func_scope = self.current_scope.find_scope(func_name)
            if not func_scope:
                for f in builtin_names:
                    if func.sym.name == '!' + f:
                        args = list(map(self.visit, node.args))
                        return SYSCALL(func.sym.name[1:], args)
                print(self._err_info(node))
                raise TypeError('{} is not callable'.format(func.sym.name))
            elif func_scope.is_class():
                return CTOR(func_scope, args)
        return CALL(func, args)

    
    def visit_Num(self, node):
        return CONST(node.n)
    
    def visit_Str(self, node):
        return CONST(node.s)
    
    def visit_Bytes(self, node):
        print(self._err_info(node))
        raise NotImplementedError('bytes is not supported')
    
    def visit_Ellipsis(self, node):
        print(self._err_info(node))
        raise NotImplementedError('ellipsis is not supported')

    #     | Attribute(expr value, identifier attr, expr_context ctx)
    def visit_Attribute(self, node):
        value = self.visit(node.value)
        attr = node.attr
        ctx = self._nodectx2irctx(node)
        irattr = ATTR(value, attr, ctx)

        if irattr.head().name == 'self':
            scope = Type.extra(irattr.head().typ)
            if ctx & Ctx.STORE:
                scope.gen_sym(attr)
        attr_map[node] = irattr
        return irattr

    #     | Subscript(expr value, slice slice, expr_context ctx)
    
    def visit_Subscript(self, node):
        v = self.visit(node.value)
        ctx = self._nodectx2irctx(node)
        v.ctx = ctx
        s = self.visit(node.slice)
        return MREF(v, s, ctx)

    #     | Starred(expr value, expr_context ctx)
    
    def visit_Starred(self, node):
        print(self._err_info(node))
        raise NotImplementedError('starred is not supported')

    #     | Name(identifier id, expr_context ctx)
    
    def visit_Name(self, node):
        # for Python 3.3 or older
        if node.id == 'True':
            return CONST(1)
        elif node.id == 'False':
            return CONST(0)
        elif node.id == 'None':
            return CONST(None)

        parent_scope = self.current_scope.find_scope_having_name(node.id)
        if parent_scope:
            fsym = self.current_scope.gen_sym('!' + node.id)
            scope = self.current_scope.find_scope(node.id)
            if scope and scope.is_class():
                fsym.set_type(Type.klass(None, scope))
            return TEMP(fsym, self._nodectx2irctx(node))

        sym = self.current_scope.find_sym(node.id)
        if isinstance(node.ctx, ast.Load) or isinstance(node.ctx, ast.AugLoad):
            if sym is None:
                print(self._err_info(node))
                raise NameError(node.id + ' is not defined')
        else:
            if sym is None or sym.scope is not self.current_scope:
                sym = self.current_scope.add_sym(node.id)

        assert sym is not None
        return TEMP(sym, self._nodectx2irctx(node))

    #     | List(expr* elts, expr_context ctx) 
    
    def visit_List(self, node):
        items = []
        for elt in node.elts:
            item = self.visit(elt)
            items.append(item)
        return ARRAY(items)

    #     | Tuple(expr* elts, expr_context ctx)
    
    def visit_Tuple(self, node):
        print(self._err_info(node))
        raise NotImplementedError('tuple is not supported')
    
    def visit_NameConstant(self, node):
        # for Python 3.4
        if node.value is True:
            return CONST(1)
        elif node.value is False:
            return CONST(0)
        elif node.value is None:
            return CONST(None)

    
    def visit_Slice(self, node):
        print(self._err_info(node))
        raise NotImplementedError('slice is not supported')
    
    def visit_ExtSlice(self, node):
        print(self._err_info(node))
        raise NotImplementedError('ext slice is not supported')
    
    def visit_Index(self, node):
        return self.visit(node.value)

    def visit_Print(self, node):
        print(self._err_info(node))
        raise NotImplementedError('print statement is not supported')

    def _err_info(self, node):
        return error_info(node.lineno)

class IRTranslator(object):
    def __init__(self):
        self.status = {}

    def translate(self, source):
        tree = ast.parse(source)

        fnvisitor = FunctionVisitor()
        fnvisitor.visit(tree)

        comptransformer = CompareTransformer()
        comptransformer.visit(tree)
        augassigntransformer = AugAssignTransformer()
        augassigntransformer.visit(tree)

        visitor = Visitor()
        visitor.visit(tree)
        global_scope = visitor.result()

        attrvisitor = AttributeVisitor()
        attrvisitor.visit(tree)

        return global_scope

def main():
    translator = IRTranslator()
    global_scope = translator.translate(sys.argv[1])
    Scope.dump()

if __name__ == '__main__':
    main()
        
