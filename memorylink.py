from ir import TEMP
from scope import MemLink
from env import env
from symbol import function_name
from irvisitor import IRVisitor
from type import Type

class MemoryLinkMaker(IRVisitor):
    def __init__(self):
        super().__init__()

    def visit_CALL(self, ir):
        #TODO: pass by name
        #TODO: check arg count
        for i, arg in enumerate(ir.args):
            if isinstance(arg, TEMP) and arg.sym.typ is Type.list_int_t:
                func_name = function_name(ir.func.sym)
                meminfo = self.scope.meminfos[arg.sym]
                meminfo.shared = True
                callee = self.scope.find_func_scope(func_name)
                for callee_meminfo in callee.meminfos.values():
                    if callee_meminfo.ref_index == i:
                        callee_meminfo.append_src(self.scope, meminfo)
                        linked_meminfo = MemLink(None, callee_meminfo)
                        break
                else:
                    assert linked_meminfo
                meminfo.links[callee].append(linked_meminfo)


class MemoryInstanceLinkMaker:
    def __init__(self):
        pass

    def process(self, scope):
        self.scope = scope
        for dfg in scope.dfgs(bottom_up=False):
            for node in dfg.get_scheduled_nodes():
                if node.is_stm():
                    self.visit(node.tag, node)

    def visit_UNOP(self, ir, node):
        ir.exp = self.visit(ir.exp, node)
        return ir

    def visit_BINOP(self, ir, node):
        ir.left = self.visit(ir.left, node)
        ir.right = self.visit(ir.right, node)
        return ir

    def visit_RELOP(self, ir, node):
        ir.left = self.visit(ir.left, node)
        ir.right = self.visit(ir.right, node)
        return ir

    def visit_CALL(self, ir, node):
        #TODO: pass by name
        #TODO: check arg count
        for i, arg in enumerate(ir.args):
            a = self.visit(arg, node)
            ir.args[i] = a
            if isinstance(a, TEMP) and arg.sym.typ is Type.list_int_t:
                func_name = function_name(ir.func.sym)
                inst_name = '{}_{}'.format(func_name, node.instance_num)

                meminfo = self.scope.meminfos[a.sym]
                meminfo.shared = True

                callee = self.scope.find_func_scope(func_name)

                for callee_meminfo in callee.meminfos.values():
                    if callee_meminfo.ref_index == i:
                        #callee_meminfo.set_length(meminfo.length)
                        linked_meminfo = (inst_name, callee_meminfo)
                        break
                else:
                    assert linked_meminfo
                meminfo.links[callee].remove(MemLink(None, callee_meminfo))
                meminfo.links[callee].append(linked_meminfo)
        return ir

    def visit_SYSCALL(self, ir, node):
        for i, arg in enumerate(ir.args):
            ir.args[i] = self.visit(arg, node)
        return ir

    def visit_CONST(self, ir, node):
        return ir

    def visit_MREF(self, ir, node):
        ir.offset = self.visit(ir.offset, node)
        return ir

    def visit_MSTORE(self, ir, node):
        ir.offset = self.visit(ir.offset, node)
        ir.exp = self.visit(ir.exp, node)
        return ir

    def visit_ARRAY(self, ir, node):
        for i, item in enumerate(ir.items):
            ir.items[i] = self.visit(item, node)
        return ir

    def visit_TEMP(self, ir, node):
        return ir

    def visit_EXPR(self, ir, node):
        ir.exp = self.visit(ir.exp, node)
 
    def visit_PARAM(self, ir, node):
        pass

    def visit_CJUMP(self, ir, node):
        ir.exp = self.visit(ir.exp, node)

    def visit_JUMP(self, ir, node):
        pass

    def visit_MCJUMP(self, ir, node):
        for i, c in enumerate(ir.conds):
            ir.conds[i] = self.visit(c, node)

    def visit_RET(self, ir, node):
        pass

    def visit_MOVE(self, ir, node):
        src = self.visit(ir.src, node)
        dst = self.visit(ir.dst, node)

    def visit(self, ir, node):
        method = 'visit_' + ir.__class__.__name__
        visitor = getattr(self, method, None)
        return visitor(ir, node)

