from .ir import *
from .utils import replace_item, remove_except_one
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
        self.parent = None
        self.is_hyperblock = False

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
        return self.order < other.order

    def connect(self, next_block):
        self.succs.append(next_block)
        next_block.preds.append(self)

    def connect_loop(self, next_block):
        self.connect(next_block)
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
        replace_item(self.succs, old, new, all=True)
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
        replace_item(self.succs_loop, old, new, all=True)

    def replace_pred(self, old, new):
        replace_item(self.preds, old, new, all=True)

    def replace_pred_loop(self, old, new):
        replace_item(self.preds_loop, old, new, all=True)

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
        b.is_hyperblock = self.is_hyperblock
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
            targets[0].preds = remove_except_one(targets[0].preds, self)
            targets[0].path_exp = self.path_exp
        else:
            return

        if self.is_hyperblock:
            return
        usedef = self.scope.usedef
        for cond in conds:
            if cond.is_a(CONST):
                continue
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
        head.parent = self
        for body in bodies:
            body.parent = self

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
