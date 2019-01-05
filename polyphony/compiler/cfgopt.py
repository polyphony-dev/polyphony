from collections import deque
from .block import Block
from .dominator import DominatorTreeBuilder
from .env import env
from .ir import *
from .irhelper import reduce_relexp, is_port_method_call
from .type import Type
from .usedef import UseDefDetector
from .utils import remove_except_one
from logging import getLogger
logger = getLogger(__name__)


def can_merge_synth_params(params1, params2):
    # TODO
    return params1 == params2


class BlockReducer(object):
    def process(self, scope):
        self.scope = scope
        if scope.is_class():
            return
        self.removed_blks = []
        while True:
            self._merge_unidirectional_block(scope)
            self._remove_empty_blocks(scope)
            if not self.removed_blks:
                break
            else:
                self._merge_duplicate_paths(scope)
                self.removed_blks = []
        self._order_blocks(scope)

    def _order_blocks(self, scope):
        for blk in scope.traverse_blocks():
            blk.order = -1
        Block.set_order(scope.entry_block, 0)

    def _merge_duplicate_paths(self, scope):
        for block in scope.traverse_blocks():
            if not block.stms:
                continue
            stm = block.stms[-1]
            if stm.is_a(CJUMP) and stm.true is stm.false:
                block.stms.pop()
                block.append_stm(JUMP(stm.true))
                block.succs = [stm.true]
                # leave only first mathced item
                stm.true.preds = remove_except_one(stm.true.preds, block)
                assert 1 == stm.true.preds.count(block)
            elif stm.is_a(MCJUMP) and len(set(stm.targets)) == 1:
                block.stms.pop()
                block.append_stm(JUMP(stm.targets[0]))
                block.succs = [stm.targets[0]]
                stm.targets[0].preds = remove_except_one(stm.targets[0].preds, block)
                assert 1 == stm.targets[0].preds.count(block)

    def _merge_unidirectional_block(self, scope):
        for block in scope.traverse_blocks():
            #check unidirectional
            # TODO: any jump.typ
            if (len(block.preds) == 1 and
                    len(block.preds[0].succs) == 1 and
                    can_merge_synth_params(block.synth_params, block.preds[0].synth_params)):
                pred = block.preds[0]
                assert pred.stms[-1].is_a(JUMP)
                assert pred.succs[0] is block
                assert not pred.succs_loop

                pred.stms.pop()  # remove useless jump
                # merge stms
                for stm in block.stms:
                    pred.append_stm(stm)

                #deal with block links
                for succ in block.succs:
                    succ.replace_pred(block, pred)
                    succ.replace_pred_loop(block, pred)
                pred.succs = block.succs
                pred.succs_loop = block.succs_loop
                if block is scope.exit_block:
                    scope.exit_block = pred

                logger.debug('remove unidirectional block ' + str(block.name))
                self._remove_block(block)
                if not pred.is_hyperblock:
                    pred.is_hyperblock = block.is_hyperblock

    def remove_empty_block(self, block):
        if len(block.stms) > 1:
            return False
        if block is block.scope.entry_block:
            return False
        if block.preds_loop or block.succs_loop:
            return False
        if block.stms and block.stms[0].is_a(JUMP):
            assert len(block.succs) == 1
            succ = block.succs[0]
            idx = succ.preds.index(block)
            succ.remove_pred(block)
            for pred in block.preds:
                succ.preds.insert(idx, pred)
                idx += 1
                pred.replace_succ(block, succ)
            logger.debug('remove empty block ' + block.name)
            return True
        return False

    def _remove_empty_blocks(self, scope):
        for block in scope.traverse_blocks():
            if self.remove_empty_block(block):
                self._remove_block(block)

    def _remove_block(self, blk):
        self.removed_blks.append(blk)
        self.scope.remove_block_from_region(blk)


class PathExpTracer(object):
    def process(self, scope):
        self.scope = scope
        for blk in scope.traverse_blocks():
            blk.order = -1
        Block.set_order(scope.entry_block, 0)
        tree = DominatorTreeBuilder(scope).process()
        tree.dump()
        self.tree = tree
        self.worklist = deque()
        self.worklist.append(scope.entry_block)
        while self.worklist:
            blk = self.worklist.popleft()
            self.traverse_dtree(blk)

    def make_path_exp(self, blk, parent):
        blk.path_exp = parent.path_exp
        if len(parent.succs) > 1 and len(blk.preds) == 1:
            r = self.scope.find_region(parent)
            if r.head is parent and r is not self.scope.top_region() and blk not in r.bodies:
                # do not merge path expression for the loop exit
                if parent.path_exp:
                    blk.path_exp = parent.path_exp.clone()
            else:
                blk.path_exp = merge_path_exp(parent, blk)

    def traverse_dtree(self, blk):
        if not blk.stms:
            return
        parent = self.tree.get_parent_of(blk)
        if parent:
            self.make_path_exp(blk, parent)
        children = self.tree.get_children_of(blk)
        for child in children:
            self.traverse_dtree(child)


def merge_path_exp(pred, blk, idx_hint=-1):
    jump = pred.stms[-1]
    exp = None
    if jump.is_a(CJUMP):
        if blk is jump.true:
            exp = rel_and_exp(pred.path_exp, jump.exp)
        elif blk is jump.false:
            exp = rel_and_exp(pred.path_exp, UNOP('Not', jump.exp))
    elif jump.is_a(MCJUMP):
        if blk in jump.targets:
            if 1 == jump.targets.count(blk):
                idx = jump.targets.index(blk)
            elif idx_hint >= 0:
                idx = idx_hint
            else:
                assert False
            exp = rel_and_exp(pred.path_exp, jump.conds[idx])
    return exp


def rel_and_exp(exp1, exp2):
    if exp1 is None:
        return exp2
    elif exp2 is None:
        return exp1
    exp1 = reduce_relexp(exp1)
    exp2 = reduce_relexp(exp2)
    exp = RELOP('And', exp1, exp2)
    exp.lineno = exp1.lineno
    return exp


class HyperBlockBuilder(object):
    def process(self, scope):
        self.scope = scope
        self.uddetector = UseDefDetector()
        self.uddetector.table = scope.usedef
        self.diamond_nodes = deque()
        self._visited_heads = set()
        diamond_nodes = self._find_diamond_nodes()
        self._convert(diamond_nodes)

    def _update_domtree(self):
        self.tree = DominatorTreeBuilder(self.scope).process()

    def _walk_to_convergence(self, blk, path):
        b = blk
        while b:
            path.append(b)
            if len(b.preds) > 1:
                return True
            if not b.succs:
                return False
            if len(b.succs) > 1:
                return False
            if b.succs[0] in b.succs_loop:
                return False
            b = b.succs[0]

    def _find_diamond_nodes(self):
        self._update_domtree()
        for blk in self.scope.traverse_blocks():
            if len(blk.succs) <= 1:
                continue
            if blk in self._visited_heads:
                continue
            tails = []
            branches = []
            for succ in blk.succs:
                path = []
                to_convergence = self._walk_to_convergence(succ, path)
                if not to_convergence:
                    continue
                tails.append(path[-1])
                branches.append(path)
            if all([tails[0] is b for b in tails[1:]]):
                # perfect diamond-nodes
                if len(blk.succs) == len(tails):
                    return (blk, tails[0], branches)
            else:
                for tail in tails:
                    if tails.count(tail) > 1:
                        indices = [idx for idx, path in enumerate(branches) if path[-1] is tail]
                        # We should deal with only continuous indices(adjacent branches)
                        # to keep mcjump evaluation order
                        if all([(indices[i + 1] - indices[i]) == 1
                                for i in range(len(indices) - 1)]):
                            return self._duplicate_head(blk, branches, indices)

        return None

    def _duplicate_head(self, head, branches, indices):
        new_head = Block(self.scope)
        old_mj = head.stms[-1]
        mj = MCJUMP()
        mj.lineno = old_mj.lineno
        for idx in indices:
            path = branches[idx]
            br = path[0]
            assert br in head.succs
            assert old_mj.targets[idx] is br
            cond = old_mj.conds[idx]
            mj.conds.append(cond)
            mj.targets.append(br)
        if all([mj.targets[0] is t for t in mj.targets[1:]]):
            return
        for idx in indices:
            path = branches[idx]
            br = path[0]
            br.replace_pred(head, new_head)
            new_head.succs.append(br)
        new_cond = old_mj.conds[indices[0]]
        for idx in indices[1:]:
            new_cond = RELOP('Or', new_cond, old_mj.conds[idx])
        old_mj.conds[indices[0]] = new_cond
        old_mj.targets[indices[0]] = new_head
        head.succs[indices[0]] = new_head
        for idx in reversed(indices[1:]):
            old_mj.conds.pop(idx)
            old_mj.targets.pop(idx)
            head.succs.pop(idx)
        if len(old_mj.targets) == 2:
            cj = CJUMP(old_mj.conds[0], old_mj.targets[0], old_mj.targets[1])
            cj.lineno = old_mj.lineno
            head.replace_stm(head.stms[-1], cj)
        if len(mj.targets) == 2:
            cj = CJUMP(mj.conds[0], mj.targets[0], mj.targets[1])
            cj.lineno = mj.lineno
            new_head.append_stm(cj)
        else:
            new_head.append_stm(mj)
        new_head.preds = [head]
        new_head.path_exp = merge_path_exp(head, new_head)
        Block.set_order(new_head, head.order + 1)
        self._update_domtree()
        sub_branches = [branches[idx] for idx in indices]
        tail = sub_branches[0][-1]
        return (new_head, tail, sub_branches)

    def _convert(self, diamond_nodes):
        reducer = BlockReducer()
        reducer.scope = self.scope
        while diamond_nodes:
            head, tail, branches = diamond_nodes
            if self.tree.get_parent_of(tail) is head:
                # pure diamond nodes
                self._merge_diamond_blocks(head, tail, branches)
                for path in branches:
                    for blk in path[:-1]:
                        reducer.remove_empty_block(blk)
                reducer.remove_empty_block(tail)
                self._visited_heads.add(head)
            else:
                self._do_phi_reduction(head, tail, branches)
            diamond_nodes = self._find_diamond_nodes()

    def _do_phi_reduction(self, head, tail, branches):
        new_tail = Block(self.scope)
        if head.path_exp:
            new_tail.path_exp = head.path_exp
        else:
            new_tail.path_exp = CONST(1)
        removes = []
        indices = []
        for path in branches:
            if len(path) > 1:
                br = path[-2]
            else:
                br = head
            removes.append(br)
        br = removes[0]
        first_idx = tail.preds.index(br)
        indices = list(range(first_idx, first_idx + len(removes)))
        for idx, br in zip(indices, removes):
            assert tail.preds[idx] is br
        for stm in tail.stms:
            if stm.is_a(PHIBase):
                new_args = []
                new_ps = []
                old_args = []
                old_ps = []
                for idx in range(len(stm.args)):
                    if idx in indices:
                        new_args.append(stm.args[idx])
                        new_ps.append(stm.ps[idx])
                    elif stm.args[idx]:
                        old_args.append(stm.args[idx])
                        old_ps.append(stm.ps[idx])
                if all([new_args[0].symbol() is arg.symbol() for arg in new_args[1:]]):
                    newsym = self.scope.add_temp()
                    newsym.set_type(stm.var.symbol().typ.clone())
                    dst = TEMP(newsym, Ctx.STORE)
                    mv = MOVE(dst, new_args[0])
                    mv.lineno = dst.lineno = stm.var.lineno
                    new_tail.append_stm(mv)
                else:
                    new_phi = stm.clone()
                    new_phi.args = new_args
                    new_phi.ps = new_ps
                    newsym = self.scope.add_temp()
                    newsym.set_type(stm.var.symbol().typ.clone())
                    new_phi.var = TEMP(newsym, Ctx.STORE)
                    new_phi.var.lineno = stm.var.lineno
                    new_tail.append_stm(new_phi)

                arg = TEMP(newsym, Ctx.LOAD)
                arg.lineno = stm.var.lineno

                #ps = new_ps[0]
                #for p in new_ps[1:]:
                #    ps = RELOP('Or', ps, p)
                old_args.insert(first_idx, arg)
                old_ps.insert(first_idx, new_tail.path_exp)
                #old_ps.insert(first_idx, ps)
                stm.args = old_args
                stm.ps = old_ps

        for br in removes:
            old_jmp = br.stms[-1]
            old_jmp.target = new_tail
            assert br in tail.preds
            tail.preds.remove(br)
            new_tail.preds.append(br)
            #assert len(br.succs) == 1
            br.replace_succ(tail, new_tail)
        new_tail.append_stm(JUMP(tail))
        new_tail.succs = [tail]
        tail.preds.insert(first_idx, new_tail)
        Block.set_order(new_tail, tail.order)

    def _has_timing_function(self, stm):
        if stm.is_a(MOVE):
            call = stm.src
        elif stm.is_a(EXPR):
            call = stm.exp
        else:
            return False
        if call.is_a(SYSCALL):
            wait_funcs = [
                'polyphony.timing.clksleep',
                'polyphony.timing.wait_rising',
                'polyphony.timing.wait_falling',
                'polyphony.timing.wait_value',
                'polyphony.timing.wait_edge',
            ]
            return call.sym.name in wait_funcs
        elif call.is_a(CALL):
            if call.func_scope().is_method() and call.func_scope().parent.is_port():
                return True
            return False

    def _try_get_mem(self, stm):
        if stm.is_a(MOVE) and stm.src.is_a(MREF):
            return stm.src.mem
        elif stm.is_a(EXPR) and stm.exp.is_a(MSTORE):
            return stm.exp.mem
        else:
            return None

    def _try_get_port(self, stm):
        if stm.is_a(MOVE) and is_port_method_call(stm.src):
            return stm.src.func.tail()
        elif stm.is_a(EXPR) and is_port_method_call(stm.exp):
            return stm.src.func.tail()
        else:
            return None

    def _has_mem_access(self, stm):
        mem = self._try_get_mem(stm)
        if mem is None:
            return False
        if mem.symbol().typ.has_length():
            l = mem.symbol().typ.get_length()
            w = mem.symbol().typ.get_element().get_width()
            # TODO:
            if w * l < env.config.internal_ram_threshold_size:
                return False
        return True

    def _has_instance_var_modification(self, stm):
        if stm.is_a(MOVE) and stm.dst.is_a(ATTR):
            return True
        return False

    def _select_stms_for_speculation(self, head, blk):
        moves = []
        remains = []
        # We need to ignore the statement accessing the resource
        for idx, stm in enumerate(blk.stms[:-1]):
            if (stm.is_a(EXPR) or
                    self._has_timing_function(stm) or
                    self._has_mem_access(stm) or
                    self._has_instance_var_modification(stm)):
                remains.append((idx, stm))
                continue
            else:
                skip = False
                usesyms = self.scope.usedef.get_syms_used_at(stm)
                for sym in usesyms:
                    defstms = self.scope.usedef.get_stms_defining(sym)
                    remains_ = [s for _, s in remains]
                    intersection = defstms & set(remains_)
                    if intersection:
                        remains.append((idx, stm))
                        skip = True
                        break
                if skip:
                    continue
            moves.append((idx, stm))
        return moves, remains

    def _transform_special_stms_for_speculation(self, head, path_exp, path_remain_stms):
        all_cstms = []
        path_cstms = []
        cstms = []
        for idx, stm in path_remain_stms:
            if stm.is_a(CMOVE) or stm.is_a(CEXPR):
                cstm = stm
            elif stm.is_a(MOVE):
                cstm = CMOVE(path_exp.clone(), stm.dst.clone(), stm.src.clone())
            elif stm.is_a(EXPR):
                cstm = CEXPR(path_exp.clone(), stm.exp.clone())
            else:
                assert False
            stm.block.stms.remove(stm)
            self.scope.usedef.remove_stm(stm)
            cstm.lineno = stm.lineno
            cstms.append(cstm)
            all_cstms.append((idx, cstm))
            self.uddetector.visit(cstm)
        path_cstms.append(cstms)
        if len(path_cstms) > 1:
            for i, cstms in enumerate(path_cstms):
                nested_other_cstms = path_cstms[:i] + path_cstms[i + 1:]
                for cstm in cstms:
                    self.scope.add_branch_graph_edge(cstm, nested_other_cstms)

        return all_cstms

    def _merge_diamond_blocks(self, head, tail, branches):
        visited_path = set()
        for idx, path in enumerate(branches):
            if path[0] in visited_path:
                continue
            else:
                visited_path.update(set(path))
            assert tail is path[-1]
            for blk in path[:-1]:
                assert len(blk.succs) == 1
                stms_, remains_ = self._select_stms_for_speculation(head, blk)
                for _, stm in sorted(stms_, key=lambda _: _[0]):
                    head.insert_stm(-1, stm)
                for _, stm in stms_:
                    blk.stms.remove(stm)
                if remains_ and head.synth_params['scheduling'] == 'pipeline':
                    path_exp = merge_path_exp(head, path[0], idx)
                    cstms_ = self._transform_special_stms_for_speculation(head, path_exp, remains_)
                    for _, stm in sorted(cstms_, key=lambda _: _[0]):
                        head.insert_stm(-1, stm)
        head.is_hyperblock = True
