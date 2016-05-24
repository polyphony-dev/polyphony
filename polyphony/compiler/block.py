from .ir import JUMP, CJUMP, MCJUMP
from logging import getLogger
logger = getLogger(__name__)

class Block:
    blocks = []

    @classmethod
    def create(cls, nametag = 'b'):
        b = Block(nametag)
        cls.blocks.append(b)
        return b

    @classmethod
    def dump(cls):
        for blk in cls.blocks:
            logger.debug(str(blk))

    @classmethod
    def dump_schedule(cls):
        for blk in cls.blocks:
            logger.debug(blk.dump_schedule())

    @classmethod
    def make_branch_name(self, tags):
        if not tags:
            return '0'
        names = []
        for blk, boolean in tags:
            names.append(blk.num + str(boolean)[0])
        names.sort()
        return '_'.join(names)
        
    def __init__(self, name):
        self.orig_name = name
        self.stms = []
        self.succs = []
        self.preds = []
        self.succs_loop = []
        self.preds_loop = []
        self.order = -1
        self.branch_tags = []
        self.group = None # reference to BlockGroup

    def set_scope(self, scope):
        self.scope = scope
        self.num = str(len(scope.blocks)+1)
        self.name = '{}_{}{}'.format(scope.name, self.orig_name, self.num)

    def __str__(self):
        s = 'Block: (' + str(self.order) + ') ' + str(self.name) + '\n'

        bs = []
        s += ' # preds: {'
        for blk in self.preds:
            if blk in self.preds_loop:
                bs.append(blk.name+'$LOOP')
            else:
                bs.append(blk.name)
        s += ', '.join([b for b in bs])
        s += '}\n'

        bs = []
        s += ' # succs: {'
        for blk in self.succs:
            if blk in self.succs_loop:
                bs.append(blk.name+'$LOOP')
            else:
                bs.append(blk.name)
        s += ', '.join([b for b in bs])
        s += '}\n'

        #s += ' # branch_tags: {'
        #s += ', '.join([blk.name+':'+str(boolean) for blk, boolean in self.branch_tags])
        #s += '}\n'

        s += ' # code\n'
        s += '\n'.join(['  {0}'.format(stm) for stm in self.stms])
        s += '\n'
        return s

    def __repr__(self):
        return self.name

    def __lt__(self, other):
        return int(self.num) < int(other.num)

    def connect(self, next_block):
        self.succs.append(next_block)
        next_block.preds.append(self)
        #inherit pred's branch_tag
        for tag in self.branch_tags:
            if tag not in next_block.branch_tags:
                next_block.branch_tags.append(tag)

    def connect_branch(self, branch_block, boolean):
        self.connect(branch_block)
        branch_block.branch_tags.append((self, boolean))

    def connect_loop(self, next_block):
        self.succs.append(next_block)
        next_block.preds.append(self)

        self.succs_loop.append(next_block)
        next_block.preds_loop.append(self)

    def connect_break(self, next_block):
        self.succs.append(next_block)
        next_block.preds.append(self)

    def connect_continue(self, next_block):
        self.succs.append(next_block)
        next_block.preds.append(self)

    def merge_branch(self, trunk_block):
        self.branch_tags = [(blk, boolean) for blk, boolean in self.branch_tags if blk is not trunk_block]

    def append_stm(self, stm):
        stm.block = self
        self.stms.append(stm)

    def replace_stm(self, old_stm, new_stm):
        idx = self.stms.index(old_stm)
        self.stms.remove(old_stm)
        self.stms.insert(idx, new_stm)
        new_stm.block = self

    def stm(self, idx):
        if len(self.stms):
            return self.stms[idx]
        else:
            return None

    def is_branch(self):
        return self.branch_tags

class BlockTracer:
    def process(self, scope):
        self.scope = scope
        self._remove_unreachable_block(scope)
        #self._merge_unidirectional_block(scope.blocks)
        self._remove_empty_block(scope)
        self._set_order(scope.blocks[0], 0)


    def _remove_unreachable_block(self, scope):
        bs = scope.blocks[1:]
        for block in bs:
            if not block.preds:
                for succ in block.succs:
                    succ.preds.remove(block)
                scope.remove_block(block)
                logger.debug('remove block ' + block.name)
    #Block references:
    # block.succs
    # block.succs_loop
    # block.preds
    # block.preds_loop
    # stm.block
    # scope.blocks
    # scope.loop_info
    def _merge_unidirectional_block(self, blocks):
        garbage_blocks = []
        for block in blocks:
            #check unidirectional
            if len(block.preds) == 1 and len(block.preds[0].succs) == 1 and block.preds[0].stms[-1].typ == '':
                pred = block.preds[0]
                assert pred.stms[-1].is_a(JUMP)
                assert block not in self.scope.loop_infos.keys()
                assert pred.succs[0] is block
                
                #merge stms
                pred.stms.pop()
                pred.stms.extend(block.stms)

                #deal with block links
                for succ in block.succs:
                    idx = succ.preds.index(block)
                    succ.preds[idx] = pred
                    if block in succ.preds_loop:
                        idx = succ.preds_loop.index(block)
                        succ.preds_loop[idx] = pred
                pred.succs = block.succs
                pred.succs_loop = block.succs_loop

                #deal with block branch tags
                pred.branch_tags = block.branch_tags

                #set the pointer to the block to each stm
                for stm in block.stms:
                    stm.block = pred

                garbage_blocks.append(block)

        for block in garbage_blocks:
            logger.debug('remove block ' + block.name)
            blocks.remove(block)


    def _set_order(self, block, order):
        if order > block.order:
            logger.debug(block.name + ' order ' + str(order))
            block.order = order
        order += 1
        for succ in [succ for succ in block.succs if succ not in block.succs_loop]:
            self._set_order(succ, order)


    def _remove_empty_block(self, scope):
        bs = scope.blocks[:]
        for block in bs:
            if len(block.stms) == 1 and block.stms[0].is_a(JUMP) and block.stms[0].typ == '':
                target = block.stms[0].target
                target.preds.remove(block)
                self._replace_jump_target(block, target)
                scope.remove_block(block)
                logger.debug('remove empty block ' + block.name)

    def _replace_jump_target(self, old_blk, new_blk):
        for pred in old_blk.preds:
            jmp = pred.stms[-1]
            if jmp.is_a(JUMP):
                jmp.target = new_blk
            elif jmp.is_a(CJUMP):
                if jmp.true is old_blk:
                    jmp.true = new_blk
                elif jmp.false is old_blk:
                    jmp.false = new_blk
                else:
                    assert False
            elif jmp.is_a(MCJUMP):
                for i, t in enumerate(jmp.targets):
                    if t is old_blk:
                       jmp.targets[i] = new_blk 
            pred.succs.remove(old_blk)
            pred.succs.append(new_blk)
            new_blk.preds.append(pred)
        

