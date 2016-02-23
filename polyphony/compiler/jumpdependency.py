from .ir import TEMP, JUMP, CJUMP, MCJUMP

class JumpDependencyDetector:
    def process(self, scope):
        self.usedef = scope.usedef
        self.liveins = scope.liveins
        self.liveouts = scope.liveouts

        block = scope.blocks[0]
        
        #defs = []
        #self._detect_old(block, defs)
        self._detect(block)

    def _detect(self, block):
        if not block.succs:
            return

        for stm in block.stms:
            if isinstance(stm, JUMP):
                if stm.typ != '':
                    ins = self.liveins[block]
                    outs = self.liveouts[block]
                    syms = ins.union(outs)
                    stm.uses = [TEMP(s, 'Load') for s, hasloop in syms if not hasloop]
                if block.succs[0] not in block.succs_loop:
                    self._detect(block.succs[0])
                return
            elif isinstance(stm, CJUMP) or isinstance(stm, MCJUMP):
                ins = self.liveins[block]
                outs = self.liveouts[block]
                syms = ins.union(outs)
                stm.uses = [TEMP(s, 'Load') for s, hasloop in syms if not hasloop]
                if block.succs[0] not in block.succs_loop:
                    self._detect(block.succs[0])
                if block.succs[1] not in block.succs_loop:
                    self._detect(block.succs[1])
                return

            
