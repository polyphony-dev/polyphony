from collections import deque
from .dominator import DominatorTreeBuilder
from .ir import CONST, BINOP, RELOP, TEMP, MOVE, JUMP, CJUMP
from .varreplacer import VarReplacer
from .usedef import UseDefDetector
from .block import BlockTracer
from logging import getLogger
logger = getLogger(__name__)

class LoopNestTree:
    def __init__(self):
        self.nodes = []
        self.edges = []

    def add_node(self, n):
        if n not in self.nodes:
            self.nodes.append(n)
        return n

    def add_edge(self, n1, n2):
        edge = (n1, n2)
        if edge not in self.edges:
            self.edges.append(edge)

    def is_child(self, loop_head1, loop_head2):
        for h1, h2 in self.edges:
            if loop_head1 is h1 and loop_head2 is h2:
                return True
        return False

    def get_children_of(self, loop_head):
        children = []
        for h1, h2 in self.edges:
            if loop_head is h1:
                children.append(h2)
        return children

    def get_parent_of(self, loop_head):
        for h1, h2 in self.edges:
            if loop_head is h2:
                return h1
        return None

    def dump(self):
        logger.debug('loop nest tree')
        for n1, n2 in sorted(self.edges, key=lambda n: n[0].name):
            logger.debug(n1.name + ' --> ' + n2.name)

class LoopDetector:
    def __init__(self):
        pass

    def process(self, scope):
        self.scope = scope
        self.loop_infos = scope.loop_infos
        for head, loop_info in scope.loop_infos.items():
            if head is scope.blocks[0]:
                continue
            self._detect(loop_info)

        self._build_loop_nest_tree(scope)
        self._eliminate_bodies(scope)
        self._process_loop_blocks(scope)

        for head, loop_info in scope.loop_infos.items():
            logger.debug('Loop')
            logger.debug('head ' + loop_info.head.name)
            logger.debug('bodies ' + ', '.join([b.name for b in loop_info.bodies]))


    def _detect(self, loop_info):
        assert len(loop_info.head.preds_loop) == 1
        loop_end = loop_info.head.preds_loop[0]
        self._collect_tail_to_head_paths([loop_end, loop_info.exit], loop_info)
        self._collect_tail_to_head_paths(loop_info.breaks, loop_info)
        self._collect_tail_to_head_paths(loop_info.returns, loop_info)

    def _collect_tail_to_head_paths(self, tails, loop_info):
        for tail in tails:
            if tail not in self.scope.blocks:
                continue
            results = []
            self._trace_path(tail, loop_info.head, [], results)
            for path in results:
                loop_info.append_bodies(set(path))
                logger.log(0, 'path of tail to head = ' + ', '.join([p.name for p in path]))

    def _trace_path(self, frm, head, path, results):
        rewind_pos = len(path)
        path.append(frm)
        if frm is head:
            path.pop()
            return True
        for pred in frm.preds:
            if pred in frm.preds_loop:
                continue
            if self._trace_path(pred, head, path, results):
                results.append(list(path))

        path.pop()
        return False


    def _build_loop_nest_tree(self, scope):
        root = scope.blocks[0]
        bs = set(scope.blocks[1:])
        for head, loop_info in self.loop_infos.items():
            logger.debug(head.name)
            bs = bs.difference(loop_info.bodies)
        loop_info_root = scope.loop_infos[root]
        loop_info_root.append_bodies(bs)

        loop_nest_tree = LoopNestTree()
        scope.loop_nest_tree = loop_nest_tree
        loop_nest_tree.add_node(root)

        for h1 in self.loop_infos.keys():
            for h2 in self.loop_infos.keys():
                if h1 is h2:
                    continue
                if h1 in self.loop_infos[h2].bodies:
                    parent = loop_nest_tree.add_node(h2)
                    child = loop_nest_tree.add_node(h1)
                    loop_nest_tree.add_edge(parent, child)
                    continue

        #loop_nest_tree.dump()

    def _eliminate_bodies(self, scope):
        self._eliminate(scope.blocks[0])

    def _eliminate(self, head):
        children = self.scope.loop_nest_tree.get_children_of(head)
        if not children:
            return
        for c in children:
            self._eliminate(c)
            parent_loop_info = self.scope.loop_infos[head]
            child_loop_info = self.scope.loop_infos[c]
            for b in child_loop_info.bodies:
                logger.debug('eliminate ' + b.name + ' FROM ' + head.name)
                if b in parent_loop_info.bodies:
                    parent_loop_info.bodies.remove(b)

    def _process_loop_blocks(self, scope):
        all_blocks = set(scope.blocks)
        for loop_head, loop_info in self.loop_infos.items():
            if loop_head is scope.blocks[0]:
                continue
            loop_blocks = set([loop_head])
            loop_blocks = loop_blocks.union(loop_info.bodies)
            other_blocks = all_blocks.difference(loop_blocks)
            defs, uses = self._get_loop_dependency(scope.usedef, loop_head, loop_blocks, other_blocks)
            loop_info.defs = defs
            loop_info.uses = uses

        #merge child defs & uses
        for loop_head, loop_info in self.loop_infos.items():
            if loop_head is scope.blocks[0]:
                continue
            children = scope.loop_nest_tree.get_children_of(loop_head)
            if children:
                for c in children:
                    child_loop_info = scope.loop_infos[c]
                    assert child_loop_info
                    loop_info.defs = loop_info.defs.union(child_loop_info.defs)
                    loop_info.uses = loop_info.uses.union(child_loop_info.uses)

                    

    def _get_loop_dependency(self, usedef, loop_head, loop_blocks, other_blocks):
        defs = set()
        uses = set()
        for lb in loop_blocks:
            logger.log(0, 'loop block of ' + loop_head.name + ' is ' + lb.name)
            inner_def_syms = usedef.get_def_syms_by_blk(lb)
            for sym in inner_def_syms:
                useblks = usedef.get_use_blks_by_sym(sym)
                #Is this symbol used in the out of the loop?
                if other_blocks.intersection(useblks):
                    defs.add(sym)

            inner_use_syms = usedef.get_use_syms_by_blk(lb)
            for sym in inner_use_syms:
                defblks = usedef.get_def_blks_by_sym(sym)
                #Is this symbol defined in the out of the loop?
                if other_blocks.intersection(defblks):
                    uses.add(sym)

        for lb in other_blocks:
            logger.log(0, 'none loop block of ' + loop_head.name + ' is ' + lb.name)

        logger.debug('loop dependency ' + loop_head.name)
        logger.debug('defs')
        logger.debug(', '.join([str(d) for d in defs]))
        logger.debug('uses')
        logger.debug(', '.join([str(u) for u in uses]))
        return (defs, uses)


class SimpleLoopUnroll:
    ''' simplyfied loop unrolling for testbench'''
    def __init__(self):
        pass

    def process(self, scope):
        self.scope = scope
        self.loop_infos = scope.loop_infos

        root = scope.blocks[0]
        # reset ssa form
        for var in scope.usedef.get_all_vars():
            if var.sym.ancestor:
                var.sym = var.sym.ancestor
        udd = UseDefDetector()
        udd.process(scope)

        for head, loop_info in self.loop_infos.items():
            if head is root:
                continue
            blocks = [head]
            blocks.extend(sorted(loop_info.bodies, key=lambda b:b.order))
            inductions, (loop_init, loop_limit, loop_step) = self._find_induction_and_loop_range(blocks)
            logger.debug(str(loop_init))
            logger.debug(str(loop_limit))
            logger.debug(str(loop_step))
            assert loop_init.is_a(CONST)
            assert loop_limit.is_a(CONST)
            assert loop_step.is_a(CONST)
            # should success unrolling if loop is exsisting in a testbench
            if not inductions:
                return False

            unroll_blocks = blocks[1:-1]
            if len(unroll_blocks) > 1:
                return False
            unroll_block = unroll_blocks[0]
            self._unroll(inductions, loop_init.value, loop_limit.value, loop_step.value, unroll_block)

        for head, loop_info in self.loop_infos.items():
            if head is root:
                continue
            cjump = head.stms[-1]
            assert cjump.is_a(CJUMP)
            # head jumps to true block always
            next_block = cjump.true
            jump = JUMP(next_block)
            jump.block = head
            head.stms[-1] = jump
            head.succs = [next_block]
            cjump.false.preds.remove(head)

            loop_tails = [p for p in head.preds if p in loop_info.bodies]
            for tail in loop_tails:
                head.preds.remove(tail)
                cjump.false.preds = [tail]
                tail.succs = [cjump.false]
                jump = JUMP(cjump.false)
                jump.block = tail
                tail.stms = [jump]
            # grouping
            head.group = root.group
            for b in loop_info.bodies:
                b.group = root.group
        #re-order blocks
        BlockTracer()._set_order(root, 0)

        # merge loop_info
        bodies = set()
        for head, loop_info in self.loop_infos.items():
            if loop_info.name == 'L0':
                continue
            bodies = bodies.union(loop_info.bodies)
        top_loop_info = self.scope.loop_infos[root]
        top_loop_info.bodies = bodies.union(top_loop_info.bodies)
        self.scope.loop_infos.clear()
        self.scope.loop_infos[top_loop_info.head] = top_loop_info
        loop_nest_tree = LoopNestTree()
        self.scope.loop_nest_tree = loop_nest_tree
        loop_nest_tree.add_node(root)

        return True

    def _find_induction_and_loop_range(self, blocks):
        usedef = self.scope.usedef
        # loop head should contain CJUMP which having the loop-continue test
        induction = None
        loop_init = None
        loop_limit = None
        loop_step = None
        head = blocks[0]
        tails = [p for p in head.preds if p in blocks]
        # find induction & limit
        for stm in head.stms:
            if stm.is_a(CJUMP):
                assert stm.exp.is_a(TEMP) and stm.exp.sym.is_condition()
                defstms = usedef.get_def_stms_by_sym(stm.exp.sym)
                assert len(defstms) == 1
                mv = defstms.pop()
                assert mv.is_a(MOVE)
                rel = mv.src
                assert rel.is_a(RELOP) and rel.op == 'Lt'
                induction = rel.left
                loop_limit = rel.right
                break
        # find init value
        if induction:
            defstms = usedef.get_def_stms_by_sym(induction.sym)
            for stm in defstms:
                if stm.block in head.preds and stm.block not in head.preds_loop:
                    assert stm.is_a(MOVE)
                    loop_init = stm.src
                    break
        # find step value
        for tail in tails:
            defstms = usedef.get_def_stms_by_sym(induction.sym)
            for stm in defstms:
                if stm.block is tail and stm.is_a(MOVE) and stm.src.is_a(BINOP):
                    binop = stm.src
                    assert binop.op == 'Add'
                    assert binop.left.sym is induction.sym
                    loop_step = binop.right
                    break
            else:
                continue
            break
        return [induction], (loop_init, loop_limit, loop_step)

    def _get_single_assignment_vars(self, block):
        usedef = self.scope.usedef
        usevars = usedef.get_use_vars_by_blk(block)
        use_result = []
        for var in usevars:
            if var.sym.is_temp() or var.sym.is_condition():
                use_result.append(var)
        return use_result

    def _unroll(self, inductions, start, count, step, block):
        use_temps = self._get_single_assignment_vars(block)
        new_stms = []
        for i in range(start, count, step):
            for stm in block.stms:
                if stm.is_a(JUMP):
                    continue
                copystm = stm.clone()
                # make ssa form by hand for @t and @cond
                for var in use_temps:
                    new_name = var.sym.name + '#' + str(i)
                    new_sym = self.scope.inherit_sym(var.sym, new_name)
                    replacer = VarReplacer(var, TEMP(new_sym, var.ctx), self.scope.usedef)
                    replacer.current_stm = copystm
                    replacer.visit(copystm)
                if copystm.is_a(MOVE):
                    if copystm.dst.sym.is_temp() or copystm.dst.sym.is_condition():
                        new_name = copystm.dst.sym.name + '#' + str(i)
                        new_sym = self.scope.inherit_sym(copystm.dst.sym, new_name)
                        copystm.dst.sym = new_sym
                # replace induction variables
                for induction in inductions:
                    c = CONST(i)
                    replacer = VarReplacer(induction, c, self.scope.usedef)
                    replacer.current_stm = copystm
                    replacer.visit(copystm)
                new_stms.append(copystm)
                copystm.block = block
        block.stms = new_stms
        block.append_stm(JUMP(block.succs[0]))

class LoopAnalyzer:
    def __init__(self):
        pass

    def process(self, scope):
        self.scope = scope
        self.loop_infos = scope.loop_infos

        for head, loop_info in self.loop_infos.items():
            if head.name == 'L0':
                continue
            blocks = [head]
            blocks.extend(sorted(loop_info.bodies, key=lambda b:b.order))
            self._find_induction_variables(blocks)

    def _find_induction_variables(self, blocks):
        usedef = self.scope.usedef
        for blk in blocks:
            for stm in blk.stms:
                if stm.is_a(MOVE):
                    assert stm.dst.is_a(TEMP)

            
