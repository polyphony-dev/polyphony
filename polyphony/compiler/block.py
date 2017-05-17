from collections import deque
from .ir import *
from .dominator import DominatorTreeBuilder
from .utils import replace_item
from logging import getLogger
logger = getLogger(__name__)


class Block(object):
    @classmethod
    def set_order(cls, block, order):
        order += 1
        if order > block.order:
            logger.debug(block.name + ' order ' + str(order))
            block.order = order

            succs = [succ for succ in block.succs if succ not in block.succs_loop]
            for succ in succs:
                cls.set_order(succ, order)

    def __init__(self, scope, nametag='b'):
        self.nametag = nametag
        self.stms = []
        self.succs = []
        self.preds = []
        self.succs_loop = []
        self.preds_loop = []
        self.order = -1
        self.scope = scope
        scope.block_count += 1
        self.num = scope.block_count
        self.name = '{}_{}{}'.format(scope.name, self.nametag, self.num)
        self.path_exp = None
        self.synth_params = self.scope.synth_params.copy()

    def _str_connection(self):
        s = ''
        bs = []
        s += ' # preds: {'
        for blk in self.preds:
            if blk in self.preds_loop:
                bs.append(blk.name + '$LOOP')
            else:
                bs.append(blk.name)
        s += ', '.join([b for b in bs])
        s += '}\n'

        bs = []
        s += ' # succs: {'
        for blk in self.succs:
            if blk in self.succs_loop:
                bs.append(blk.name + '$LOOP')
            else:
                bs.append(blk.name)
        s += ', '.join([b for b in bs])
        s += '}\n'
        s += ' # synthesis params {}\n'.format(self.synth_params)

        return s

    def __str__(self):
        s = 'Block: (' + str(self.order) + ') ' + str(self.name) + '\n'
        s += self._str_connection()
        if self.path_exp:
            s += ' # path exp: '
            s += str(self.path_exp) + '\n'
        s += ' # code\n'
        s += '\n'.join(['  ' + str(stm) for stm in self.stms])
        s += '\n\n'
        return s

    def __repr__(self):
        return self.name

    def __lt__(self, other):
        return int(self.order) < int(other.order)

    def connect(self, next_block):
        self.succs.append(next_block)
        next_block.preds.append(self)

    def connect_loop(self, next_block):
        self.succs.append(next_block)
        next_block.preds.append(self)

        self.succs_loop.append(next_block)
        next_block.preds_loop.append(self)

    def append_stm(self, stm):
        stm.block = self
        self.stms.append(stm)

    def insert_stm(self, idx, stm):
        stm.block = self
        self.stms.insert(idx, stm)

    def replace_stm(self, old_stm, new_stm):
        replace_item(self.stms, old_stm, new_stm)
        new_stm.block = self

    def stm(self, idx):
        if len(self.stms):
            return self.stms[idx]
        else:
            return None

    def replace_succ(self, old, new):
        replace_item(self.succs, old, new)
        if isinstance(new, CompositBlock):
            return
        if self.stms:
            jmp = self.stms[-1]
            if jmp.is_a(JUMP):
                jmp.target = new
            elif jmp.is_a(CJUMP):
                if jmp.true is old:
                    jmp.true = new
                else:
                    jmp.false = new
                self._convert_if_unidirectional(jmp)
            elif jmp.is_a(MCJUMP):
                for i, t in enumerate(jmp.targets):
                    if t is old:
                        jmp.targets[i] = new
                self._convert_if_unidirectional(jmp)

    def replace_succ_loop(self, old, new):
        replace_item(self.succs_loop, old, new)

    def replace_pred(self, old, new):
        replace_item(self.preds, old, new)

    def replace_pred_loop(self, old, new):
        replace_item(self.preds_loop, old, new)

    def remove_pred(self, pred):
        assert pred in self.preds
        self.preds.remove(pred)
        if pred in self.preds_loop:
            self.preds_loop.remove(pred)

    def remove_succ(self, succ):
        assert succ in self.succs
        self.succs.remove(succ)
        if succ in self.succs_loop:
            self.succs_loop.remove(succ)

    def collect_basic_blocks(self, blocks):
        if self in blocks:
            return
        blocks.add(self)
        for succ in [succ for succ in self.succs]:
            succ.collect_basic_blocks(blocks)

    def traverse(self, visited, full=False, longitude=False):
        if self in visited:
            return
        if self not in visited:
            visited.add(self)
            yield self
        for succ in [succ for succ in self.succs if succ not in self.succs_loop]:
            yield from succ.traverse(visited, full, longitude)

    def clone(self, scope, stm_map):
        b = Block(scope, self.nametag)
        for stm in self.stms:
            new_stm = stm.clone()
            new_stm.block = b
            b.stms.append(new_stm)
            stm_map[stm] = new_stm
        b.order = self.order
        b.succs      = list(self.succs)
        b.succs_loop = list(self.succs_loop)
        b.preds      = list(self.preds)
        b.preds_loop = list(self.preds_loop)
        b.synth_params = self.synth_params.copy()
        return b

    def reconnect(self, blk_map):
        for i, succ in enumerate(self.succs):
            self.succs[i] = blk_map[succ]
        for i, succ in enumerate(self.succs_loop):
            self.succs_loop[i] = blk_map[succ]
        for i, pred in enumerate(self.preds):
            self.preds[i] = blk_map[pred]
        for i, pred in enumerate(self.preds_loop):
            self.preds_loop[i] = blk_map[pred]

    def collect_stms(self, typs):
        return [stm for stm in self.stms if stm.is_a(typs)]

    def _convert_if_unidirectional(self, jmp):
        if not self.scope.usedef:
            return
        if jmp.is_a(CJUMP):
            conds = [jmp.exp]
            targets = [jmp.true, jmp.false]
        elif jmp.is_a(MCJUMP):
            conds = jmp.conds[:]
            targets = jmp.targets[:]
        else:
            return

        if all([targets[0] is target for target in targets[1:]]):
            newjmp = JUMP(targets[0])
            newjmp.block = self
            self.stms[-1] = newjmp
            self.succs = [targets[0]]
            targets[0].path_exp = None
        else:
            return

        usedef = self.scope.usedef
        for cond in conds:
            defstms = usedef.get_stms_defining(cond.symbol())
            assert len(defstms) == 1
            stm = defstms.pop()
            usestms = usedef.get_stms_using(cond.symbol())
            if len(usestms) > 1:
                continue
            stm.block.stms.remove(stm)


class CompositBlock(Block):
    def __init__(self, scope, head, bodies, region):
        super().__init__(scope, 'composit')
        assert all([head.order < b.order for b in bodies])
        assert head.preds_loop
        self.head = head
        self.bodies = bodies
        self.region = region
        self.preds = [p for p in head.preds if p not in head.preds_loop]
        self.succs = self._find_succs([head] + bodies)
        self.order = head.order
        self.num = head.num
        self.name = '{}_{}{}'.format(scope.name, self.nametag, self.num)
        self.outer_defs = None
        self.outer_uses = None
        self.inner_defs = None
        self.inner_uses = None

    def __str__(self):
        s = 'CompositBlock: (' + str(self.order) + ') ' + str(self.name) + '\n'
        s += self._str_connection()

        s += ' # head: ' + self.head.name + '\n'
        s += ' # bodies: {'
        s += ', '.join([blk.name for blk in self.bodies])
        s += '}\n'
        if self.outer_defs:
            s += ' # outer_defs: {'
            s += ', '.join([str(d) for d in self.outer_defs])
            s += '}\n'
        if self.outer_uses:
            s += ' # outer_uses: {'
            s += ', '.join([str(u) for u in self.outer_uses])
            s += '}\n'
        if self.inner_defs:
            s += ' # inner_defs: {'
            s += ', '.join([str(d) for d in self.inner_defs])
            s += '}\n'
        if self.inner_uses:
            s += ' # inner_uses: {'
            s += ', '.join([str(u) for u in self.inner_uses])
            s += '}\n'
        bs = str(self.head)
        bs += ''.join([str(b) for b in self.bodies])
        bs = '    ' + bs.replace('\n', '\n    ')
        bs = bs[:-4]  # remove last indent
        return s + bs

    def _find_succs(self, region):
        succs = []
        for b in region:
            for succ in b.succs:
                if succ not in region:
                    succs.append(succ)
        return succs

    def collect_basic_blocks(self, blocks):
        for blk in self.region:
            blocks.add(blk)
        for succ in self.succs:
            succ.collect_basic_blocks(blocks)

    def traverse(self, visited, full=False, longitude=False):
        if longitude:
            yield from super().traverse(visited, full, longitude)
        else:
            if full:
                if self not in visited:
                    visited.add(self)
                    yield self
            yield from self.head.traverse(visited, longitude)

    def collect_basic_head_bodies(self):
        blocks = [self.head]
        for b in self.bodies:
            if not isinstance(b, CompositBlock):
                blocks.append(b)
        return blocks

    def clone(self, scope, stm_map):
        b = CompositBlock(scope, self.nametag)
        b.order = self.order
        b.succs = list(self.succs)
        b.preds = list(self.succs)
        b.head = self.head
        b.bodies = list(self.bodies)
        b.region = list(self.region)
        return b

    def reconnect(self, blk_map):
        self.head = blk_map[self.head]
        for i, b in enumerate(self.bodies):
            self.bodies[i] = blk_map[b]
        for i, b in enumerate(self.region):
            self.region[i] = blk_map[b]
        for i, succ in enumerate(self.succs):
            self.succs[i] = blk_map[succ]
        for i, pred in enumerate(self.preds):
            self.preds[i] = blk_map[pred]


def can_merge_synth_params(params1, params2):
    # TODO
    return params1 == params2


class BlockReducer(object):
    def process(self, scope):
        if scope.is_class():
            return
        self.removed_blks = []
        self._merge_unidirectional_block(scope)
        self._remove_empty_block(scope)
        self._replace_cjump(scope)
        for blk in scope.traverse_blocks():
            blk.order = -1
        Block.set_order(scope.entry_block, 0)

        # update scope's paths
        if self.removed_blks:
            for r in self.removed_blks:
                for p in scope.paths:
                    if r in p:
                        p.remove(r)

    def _replace_cjump(self, scope):
        for block in scope.traverse_blocks():
            for stm in block.stms:
                if stm.is_a(CJUMP) and stm.true is stm.false:
                    idx = block.stms.index(stm)
                    block.stms[idx] = JUMP(stm.true)
                    block.succs = [stm.true]

    def _merge_unidirectional_block(self, scope):
        for block in scope.traverse_blocks():
            #check unidirectional
            # TODO: any jump.typ
            if (len(block.preds) == 1 and
                    len(block.preds[0].succs) == 1 and
                    not block.preds[0].stms[-1].typ == 'C' and
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

                self.removed_blks.append(block)

    def _remove_empty_block(self, scope):
        for block in scope.traverse_blocks():
            if len(block.stms) > 1:
                continue
            if block is scope.entry_block:
                continue
            if block.stms and block.stms[0].is_a(JUMP):
                assert len(block.succs) == 1
                succ = block.succs[0]
                if succ in block.succs_loop:
                    if len(block.preds) > 1:
                        # do not remove a convergence loopback block
                        continue
                else:
                    succ.remove_pred(block)
                    for pred in block.preds:
                        pred.replace_succ(block, succ)
                        pred.replace_succ_loop(block, succ)
                        if pred not in succ.preds:
                            succ.preds.append(pred)
                        if pred in block.preds_loop and pred not in succ.preds_loop:
                            succ.preds_loop.append(pred)

                logger.debug('remove empty block ' + block.name)
                if block is scope.entry_block:
                    scope.entry_block = succ
                self.removed_blks.append(block)


class PathExpTracer(object):
    def process(self, scope):
        self.scope = scope
        tree = DominatorTreeBuilder(scope).process()
        tree.dump()
        self.tree = tree
        self.worklist = deque()
        self.worklist.append(scope.entry_block)
        while self.worklist:
            blk = self.worklist.popleft()
            self.traverse_dtree(blk)

    def traverse_dtree(self, blk):
        if not blk.stms:
            return
        children = self.tree.get_children_of(blk)
        jump = blk.stms[-1]
        if jump.is_a(JUMP):
            if blk.path_exp:
                for c in children:
                    c.path_exp = blk.path_exp
            # Unlike other jump instructions,
            # the target of JUMP may be a confluence node
            if jump.target.path_exp:
                parent_blk = self.tree.get_parent_of(blk)
                jump.target.path_exp = parent_blk.path_exp
            elif jump.target in blk.succs_loop:
                pass
            else:
                jump.target.path_exp = blk.path_exp
        elif jump.is_a(CJUMP):
            if blk.path_exp:
                for c in children:
                    if c is jump.true:
                        exp = self.reduce_And_exp(blk.path_exp, jump.exp)
                        if exp:
                            c.path_exp = exp
                        else:
                            c.path_exp = RELOP('And', blk.path_exp, jump.exp)
                    elif c is jump.false:
                        exp = self.reduce_And_exp(blk.path_exp, UNOP('Not', jump.exp))
                        if exp:
                            c.path_exp = exp
                        else:
                            c.path_exp = RELOP('And', blk.path_exp, UNOP('Not', jump.exp))
                    else:
                        c.path_exp = blk.path_exp
            else:
                jump.true.path_exp = jump.exp
                if jump.exp.is_a(CONST):
                    if jump.exp.value != 0:
                        jump.false.path_exp = CONST(0)
                    else:
                        jump.false.path_exp = CONST(1)
                else:
                    jump.false.path_exp = UNOP('Not', jump.exp)
        elif jump.is_a(MCJUMP):
            if blk.path_exp:
                for c in children:
                    if c in jump.targets:
                        idx = jump.targets.index(c)
                        exp = self.reduce_And_exp(blk.path_exp, jump.conds[idx])
                        if exp:
                            c.path_exp = exp
                        else:
                            c.path_exp = RELOP('And', blk.path_exp, jump.conds[idx])
                    else:
                        c.path_exp = blk.path_exp
            else:
                for t, cond in zip(jump.targets, jump.conds):
                    t.path_exp = cond
        for child in children:
            self.traverse_dtree(child)

    def reduce_And_exp(self, exp1, exp2):
        if exp1.is_a(CONST):
            if exp1.value != 0 or exp1.value is True:
                return exp2
            else:
                return exp1
        elif exp2.is_a(CONST):
            if exp2.value != 0 or exp2.value is True:
                return exp1
            else:
                return exp2
        if exp1.is_a(TEMP) and exp2.is_a(UNOP) and exp2.op == 'Not' and exp1.sym is exp2.exp.sym:
            return CONST(0)
        return None
