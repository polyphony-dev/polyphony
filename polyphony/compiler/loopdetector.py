from .ir import CONST, BINOP, RELOP, TEMP, ATTR, MOVE, JUMP, CJUMP
from .irvisitor import IRVisitor
from .graph import Graph
from .varreplacer import VarReplacer
from .usedef import UseDefDetector
from .block import Block, CompositBlock
from logging import getLogger
logger = getLogger(__name__)


class LoopNestTree(Graph):
    def set_root(self, n):
        self.add_node(n)
        self.root = n

    def traverse(self):
        return reversed(self.bfs_ordered_nodes())

    def is_child(self, loop_head1, loop_head2):
        return loop_head2 in self.succs(loop_head1)

    def is_leaf(self, loop_head):
        return not self.succs(loop_head)

    def get_children_of(self, loop_head):
        return self.succs(loop_head)

    def get_parent_of(self, loop_head):
        return self.preds(loop_head)


class LoopDetector(object):
    def __init__(self):
        pass

    def process(self, scope):
        self.scope = scope
        scope.loop_nest_tree = LoopNestTree()

        ordered_blks = []
        visited = []
        head = scope.entry_block
        self._process_walk(head, ordered_blks, visited)
        assert head is ordered_blks[-1]

        lblks, blks = self._make_loop_block_bodies(ordered_blks)

        self._add_loop_tree_entry(head, lblks)
        self.scope.loop_nest_tree.set_root(head)

        LoopDependencyDetector().process(scope)
        LoopVariableDetector().process(scope)
        #lbd = LoopBlockDestructor()
        #lbd.process(scope)

    def _make_loop_block(self, head, loop_region):
        lblks, blks = self._make_loop_block_bodies(loop_region)
        bodies = sorted(lblks + blks, key=lambda b: b.order)
        lb = CompositBlock(self.scope, head, bodies, [head] + loop_region)
        self._add_loop_tree_entry(lb, lblks)
        return lb

    def _make_loop_block_bodies(self, blks):
        sccs = self._extract_sccs(blks)
        lblks = []
        for scc in sccs:
            head = scc.pop()
            loop_region = scc

            # shrink blocks
            blks = [b for b in blks if b is not head and b not in loop_region]
            assert blks

            lb = self._make_loop_block(head, loop_region)
            lblks.append(lb)

            # re-connect
            for p in lb.preds:
                p.replace_succ(lb.head, lb)
            for s in lb.succs:
                s.replace_pred([lb.head] + lb.bodies, lb)

        return lblks, blks

    def _extract_sccs(self, ordered_blks):
        sccs = []
        for scc in self._find_scc(ordered_blks[:]):
            if len(scc) > 1:
                # we have to keep the depth-first-search order
                blks = [b for b in ordered_blks if b in scc]
                sccs.append(blks)
        return sccs

    # 'scc' is 'strongly connected components'
    def _find_scc(self, blks):
        sccs = []
        visited = []
        while blks:
            blk = blks[-1]
            scc = []
            self._process_back_walk(blk, blks, visited, scc)
            sccs.append(scc)
        return sccs

    def _process_walk(self, blk, blks, visited):
        visited.append(blk)
        if blk.succs:
            for succ in blk.succs:
                if succ not in visited:
                    self._process_walk(succ, blks, visited)
        blks.append(blk)

    def _process_back_walk(self, blk, blks, visited, scc):
        scc.append(blk)
        visited.append(blk)
        blks.remove(blk)
        for pred in blk.preds:
            if pred not in visited and pred in blks:
                self._process_back_walk(pred, blks, visited, scc)

    def _add_loop_tree_entry(self, parent, children):
        self.scope.loop_nest_tree.add_node(parent)
        for child in children:
            self.scope.loop_nest_tree.add_edge(parent, child)


class LoopVariableDetector(IRVisitor):
    def process(self, scope):
        self.usedef = scope.usedef
        super().process(scope)

    def visit_MOVE(self, ir):
        assert ir.dst.is_a([TEMP, ATTR])
        sym = ir.dst.symbol()
        if sym.is_temp() or sym.is_return() or sym.typ.is_port():
            return
        if ir.src.is_a([TEMP, ATTR]):
            src_sym = ir.src.symbol()
            if src_sym.is_param() or src_sym.typ.is_port():
                return
        if self._has_depend_cycle(ir, sym):
            sym.add_tag('induction')

    def _has_depend_cycle(self, start_stm, sym):
        def _has_depend_cycle_r(start_stm, sym, visited):
            stms = self.usedef.get_stms_using(sym)
            if start_stm in stms:
                return True
            for stm in stms:
                if stm in visited:
                    continue
                visited.add(stm)
                defsyms = self.usedef.get_syms_defined_at(stm)
                for defsym in defsyms:
                    if _has_depend_cycle_r(start_stm, defsym, visited):
                        return True
            return False
        visited = set()
        return _has_depend_cycle_r(start_stm, sym, visited)


# hierarchize
class LoopDependencyDetector(object):
    def process(self, scope):
        all_blks = set()
        scope.entry_block.collect_basic_blocks(all_blks)
        for lb in scope.loop_nest_tree.traverse():
            if lb is scope.loop_nest_tree.root:
                break
            outer_region = all_blks.difference(set(lb.region))
            inner_region = set(lb.region).difference(set([lb.head])).difference(set(lb.bodies))
            od, ou, id, iu = self._get_loop_block_dependency(scope.usedef,
                                                             lb,
                                                             outer_region,
                                                             inner_region)
            lb.outer_defs = od
            lb.outer_uses = ou
            lb.inner_defs = id
            lb.inner_uses = iu

    def _get_loop_block_dependency(self, usedef, lb, outer_region, inner_region):
        outer_defs = set()
        outer_uses = set()
        inner_defs = set()
        inner_uses = set()
        blocks = [lb.head] + lb.bodies
        for blk in blocks:
            usesyms = usedef.get_syms_used_at(blk)
            for sym in usesyms:
                defblks = usedef.get_blks_defining(sym)
                # Is this symbol used in the out of the loop?
                intersect = outer_region.intersection(defblks)
                if intersect:
                    outer_defs.add(sym)
                intersect = inner_region.intersection(defblks)
                if intersect:
                    inner_defs.add(sym)

            defsyms = usedef.get_syms_defined_at(blk)
            for sym in defsyms:
                useblks = usedef.get_blks_using(sym)
                # Is this symbol used in the out of the loop?
                intersect = outer_region.intersection(useblks)
                if intersect:
                    outer_uses.add(sym)
                intersect = inner_region.intersection(useblks)
                if intersect:
                    inner_uses.add(sym)

        return (outer_defs, outer_uses, inner_defs, inner_uses)


class LoopBlockDestructor(object):
    def __init__(self):
        pass

    def process(self, scope):
        for lb in scope.loop_nest_tree.traverse():
            if lb is scope.loop_nest_tree.root:
                break
            lb.preds
            # re-connect
            for p in lb.preds:
                p.replace_succ(lb, lb.head)
            for s in lb.succs:
                for body in [lb.head] + lb.bodies:
                    if s in body.succs:
                        s.replace_pred(lb, body)
                        break
        scope.loop_nest_tree = None
        for blk in scope.traverse_blocks():
            blk.order = -1
        Block.set_order(scope.entry_block, 0)


class SimpleLoopUnroll(object):
    '''simplyfied loop unrolling for testbench'''
    def __init__(self):
        pass

    def process(self, scope):
        self.scope = scope

        entry = scope.entry_block
        # reset ssa form
        for var in scope.usedef.get_all_vars():
            if var.symbol().ancestor:
                var.set_symbol(var.symbol().ancestor)
        udd = UseDefDetector()
        udd.process(scope)

        for c in self.scope.loop_nest_tree.get_children_of(entry):
            if self.scope.loop_nest_tree.is_leaf(c):
                self._process(c)
            else:
                raise NotImplementedError('cannot unroll the nested loop')
        for blk in scope.traverse_blocks():
            blk.order = -1
        Block.set_order(entry, 0)

    def _process(self, blk):
        assert isinstance(blk, CompositBlock)
        blocks = blk.collect_basic_head_bodies()

        inductions, (loop_init, loop_limit, loop_step) = self._find_induction_and_loop_range(blocks)
        logger.debug(str(loop_init))
        logger.debug(str(loop_limit))
        logger.debug(str(loop_step))
        if (not inductions or not loop_init.is_a(CONST) or
                not loop_limit.is_a(CONST) or not loop_step.is_a(CONST)):
            raise NotImplementedError('cannot unroll the loop')

        unroll_blocks = blocks[1:-1]
        if len(unroll_blocks) > 1:
            raise NotImplementedError('cannot unroll the loop containing branches')
        unroll_block = unroll_blocks[0]
        self._unroll(inductions, loop_init.value, loop_limit.value, loop_step.value, unroll_block)

        cjump = blk.head.stms[-1]
        assert cjump.is_a(CJUMP)
        # head jumps to true block always
        next_block = cjump.true
        jump = JUMP(next_block)
        jump.block = blk.head
        jump.lineno = cjump.lineno
        blk.head.stms[-1] = jump
        blk.head.succs = [next_block]
        if blk.head in cjump.false.preds:
            cjump.false.preds.remove(blk.head)

        loop_tails = [p for p in blk.head.preds if p in blk.bodies]
        for tail in loop_tails:
            blk.head.preds.remove(tail)
            cjump.false.preds = [tail]
            tail.succs = [cjump.false]
            tail.succs_loop = []
            jump = JUMP(cjump.false)
            jump.block = tail
            jump.lineno = cjump.lineno
            tail.stms = [jump]

        #re-order blocks
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
                defstms = usedef.get_stms_defining(stm.exp.sym)
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
            defstms = usedef.get_stms_defining(induction.sym)
            for stm in defstms:
                if stm.block in head.preds and stm.block not in head.preds_loop:
                    assert stm.is_a(MOVE)
                    loop_init = stm.src
                    break
        # find step value
        for tail in tails:
            defstms = usedef.get_stms_defining(induction.sym)
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
        usevars = usedef.get_vars_used_at(block)
        use_result = []
        for var in usevars:
            if var.symbol().is_temp() or var.symbol().is_condition():
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
        jump = JUMP(block.succs[0])
        jump.lineno = 1
        block.append_stm(jump)
