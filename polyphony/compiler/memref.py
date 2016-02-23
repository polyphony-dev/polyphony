from collections import deque, defaultdict
from .varreplacer import VarReplacer
from .ir import CONST, TEMP, ARRAY, CALL, EXPR, MREF, MSTORE, MOVE, PHI
from .symbol import Symbol, function_name
from .type import Type
from .irvisitor import IRTransformer, IRVisitor
from .env import env
from .scope import Scope
from logging import getLogger
logger = getLogger(__name__)


class MemRefNode:
    SRC  = 0x00000001
    WR   = 0x00000002

    id = 0
    def __init__(self, sym, scope):
        self.sym = sym
        self.scope = scope
        self.flags = 0
        self.width = 32 # TODO
        self.length = -1
        self.initstm = None
        self.param_index = -1
        self.preds = set()
        self.succs = set()

    def __str__(self):
        s = '{}{}:'.format(self.sym, self.scope.name)
        s += '[{}]:flags={}:ref={}:initstm={}\n'.format(self.length, self.flags, self.param_index, self.initstm)
        s += '\tpreds\n'
        s += '\t\t'+', '.join(['{}{}'.format(pred.sym, pred.scope.name) for pred in self.preds])
        s += '\n'
        s += '\tsuccs\n'
        s += '\t\t'+', '.join(['{}{}'.format(succ.sym, succ.scope.name) for succ in self.succs])
        s += '\n'
        return s

    def __repr__(self):
        return self.__str__()

    def __lt__(self, other):
        return self.sym < other.sym

    def add_pred(self, pred):
        self.preds.add(pred)
        max_length = max([p.length for p in self.preds])
        self.length = max_length

    def add_succ(self, succ):
        self.succs.add(succ)

    def propagate_preds(self, fn):
        fn(self)
        for s in self.preds:
            s.propagate_preds(fn)

    def propagate_succs(self, fn):
        fn(self)
        for s in self.succs:
            s.propagate_succs(fn)

    def set_initstm(self, initstm):
        assert initstm
        assert isinstance(initstm, MOVE) and isinstance(initstm.src, ARRAY)
        self.length = len(initstm.src.items)
        self.flags |= MemRefNode.SRC
        self.initstm = initstm

    def set_writable(self):
        self.flags |= MemRefNode.WR

    def is_writable(self):
        return self.flags & MemRefNode.WR

    def is_joinable(self):
        return len(self.preds) > 1

    def is_forkable(self):
        return len(self.succs) > 1

    def set_param_index(self, index):
        self.param_index = index

    def is_param(self):
        return self.param_index != -1

        
class MemRefGraph:
    def __init__(self):
        self.nodes = {}
        self.edges = {}
        self.instance_edges = {}

    def __str__(self):
        s = 'MemRefGraph\n'
        for node in self.nodes.values():
            s += str(node)
        for (src, dst), inst_name in self.instance_edges.items():
            s += '{} => {}:{}\n'.format(src, inst_name, dst)
        return s
        
    def add_node(self, node):
        logger.debug('add_node ' + str(node))
        self.nodes[node.sym] = node

    def node(self, sym):
        if sym in self.nodes:
            return self.nodes[sym]
        return None
        
    def add_edge(self, src, dst):
        src.add_succ(dst)
        dst.add_pred(src)
        self.edges[(src.sym, dst.sym)] = (src, dst)

    def add_instance_edge(self, src, dst, inst_name):
        self.instance_edges[(src.sym, dst.sym)] = inst_name

    def remove_node(self, node):
        logger.debug('remove_node ' + str(node))
        for pred in node.preds:
            pred.succs.remove(node)
        for succ in node.succs:
            succ.preds.remove(node)
        del self.nodes[node.sym]

    def collect_roots(self):
        for node in self.nodes.values():
            if not node.preds:
                yield node

    def collect_node_roots(self, node):
        if not node.preds:
            yield node
        for pred in node.preds:
            for n in self.collect_node_roots(pred):
                yield n

    def collect_writable(self, scope):
        for node in filter(lambda n: n.scope is scope, self.nodes.values()):
            if node.is_writable():
                yield node

    def collect_readonly(self, scope):
        for node in filter(lambda n: n.scope is scope, self.nodes.values()):
            if not node.is_writable():
                yield node

    def collect_inst_succs(self, node):
        for (src, dst), inst_name in self.instance_edges.items():
            if src is node.sym:
                yield inst_name, self.node(dst)

    def find_param_node(self, scope, param_index):
        assert len(scope.params) > param_index
        p, _, _ = scope.params[param_index]
        assert Type.is_list(p.typ)
        memnode = Type.extra(p.typ)
        assert memnode is not None
        return memnode

    def get_single_root(self, node):
        roots = [root for root in self.collect_node_roots(node)]
        if len(roots) > 1:
            return None
        return roots[0]

    def get_length(self, node):
        root = self.get_single_root(node)
        if root:
            return root.length
        else:
            return -1

    def is_path_exist(self, frm, to):
        for succ in frm.succs:
            if succ is to:
                return True
            if self.is_path_exist(succ, to):
                return True
        return False

    def is_live_node(self, node):
        return node.sym in self.nodes


class MemRefGraphBuilder(IRTransformer):
    def __init__(self):
        super().__init__()
        self.mrg = env.memref_graph = MemRefGraph()

    def process_all(self):
        scopes = Scope.get_scopes(bottom_up=True)
        for s in scopes:
            self.process(s)

    def visit_UNOP(self, ir):
        ir.exp = self.visit(ir.exp)
        return ir

    def visit_BINOP(self, ir):
        ir.left = self.visit(ir.left)
        ir.right = self.visit(ir.right)
        return ir

    def visit_RELOP(self, ir):
        ir.left = self.visit(ir.left)
        ir.right = self.visit(ir.right)
        return ir

    def visit_CALL(self, ir):
        for i in range(len(ir.args)):
            ir.args[i] = self.visit(ir.args[i])

        for i, arg in enumerate(ir.args):
            if isinstance(arg, TEMP) and Type.is_list(arg.sym.typ):
                memnode = self.mrg.node(arg.sym)
                param_node = self.mrg.find_param_node(ir.func_scope, i)
                self.mrg.add_edge(memnode, param_node)

        return ir

    def visit_SYSCALL(self, ir):
        for i in range(len(ir.args)):
            ir.args[i] = self.visit(ir.args[i])
        return ir

    def visit_CONST(self, ir):
        return ir

    def visit_MREF(self, ir):
        ir.offset = self.visit(ir.offset)
        ir.mem = self.visit(ir.mem)
        return ir

    def visit_MSTORE(self, ir):
        ir.offset = self.visit(ir.offset)
        ir.mem = self.visit(ir.mem)
        ir.exp = self.visit(ir.exp)
        memnode = Type.extra(ir.mem.sym.typ)
        memnode.set_writable()
        return ir

    def visit_ARRAY(self, ir):
        for i in range(len(ir.items)):
            ir.items[i] = self.visit(ir.items[i])
        return ir

    def visit_TEMP(self, ir):
        return ir

    def visit_EXPR(self, ir):
        ir.exp = self.visit(ir.exp)
        self.new_stms.append(ir)

    def visit_CJUMP(self, ir):
        ir.exp = self.visit(ir.exp)
        self.new_stms.append(ir)

    def visit_MCJUMP(self, ir):
        for i in range(len(ir.conds)):
            ir.conds[i] = self.visit(ir.conds[i])
        self.new_stms.append(ir)

    def visit_JUMP(self, ir):
        self.new_stms.append(ir)

    def visit_RET(self, ir):
        ir.exp = self.visit(ir.exp)
        self.new_stms.append(ir)

    def visit_MOVE(self, ir):
        ir.src = self.visit(ir.src)
        ir.dst = self.visit(ir.dst)

        if isinstance(ir.src, ARRAY):
            memsym = ir.dst.sym
            assert Type.is_list(memsym.typ)
           
            memnode = MemRefNode(memsym, self.scope)
            memnode.set_initstm(ir)
            if not all(isinstance(item, CONST) for item in ir.src.items):
                memnode.set_writable()
            self.mrg.add_node(memnode)
            memsym.set_type(Type.list(Type.int_t, memnode))

        elif isinstance(ir.src, TEMP) and ir.src.sym.is_param() and Type.is_list(ir.src.sym.typ):
            param = ir.src.sym
            memsym = ir.dst.sym
            
            memnode = MemRefNode(memsym, self.scope)
            memnode.set_param_index(self.scope.get_param_index(param))
            self.mrg.add_node(memnode)
            param.set_type(Type.list(Type.int_t, memnode))
            memsym.set_type(Type.list(Type.int_t, memnode))

        self.new_stms.append(ir)

    def visit_PHI(self, ir):
        if Type.is_list(ir.var.sym.typ):
            memnode = MemRefNode(ir.var.sym, self.scope)
            self.mrg.add_node(memnode)
            for arg, blk in ir.args:
                pred = self.mrg.node(arg.sym)
                self.mrg.add_edge(pred, memnode)
            ir.var.sym.set_type(Type.list(Type.int_t, memnode))
        self.new_stms.append(ir)


class MemRefEdgeColoring:
    def __init__(self):
        self.mrg = env.memref_graph

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
        func_name = function_name(ir.func.sym)
        inst_name = '{}_{}'.format(func_name, node.instance_num)
        
        for i, arg in enumerate(ir.args):
            a = self.visit(arg, node)
            ir.args[i] = a
            if isinstance(a, TEMP) and Type.is_list(arg.sym.typ):
                p, _, _ = ir.func_scope.params[i]
                assert Type.is_list(p.typ)
                param_memnode = Type.extra(p.typ)
                memnode = self.mrg.node(a.sym)
                # param memnode might be removed in the rom elimination of ConstantFolding
                if self.mrg.is_live_node(param_memnode):
                    assert param_memnode in memnode.succs
                    self.mrg.add_instance_edge(memnode, param_memnode, inst_name)
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

    def visit_PHI(self, ir, node):
        pass

    def visit(self, ir, node):
        method = 'visit_' + ir.__class__.__name__
        visitor = getattr(self, method, None)
        return visitor(ir, node)

