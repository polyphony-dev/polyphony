from collections import defaultdict
from logging import getLogger
logger = getLogger(__name__)

class Liveness:
    def __init__(self):
        self.liveins = defaultdict(set)
        self.liveouts = defaultdict(set)

    def process(self, scope):
        usedef = scope.usedef
        syms = usedef.get_all_syms()
        for sym in syms:
            logger.log(0, sym.name + ' paths')
            defblks = usedef.get_def_blks_by_sym(sym)
            useblks = usedef.get_use_blks_by_sym(sym)
            for defblk in defblks:
                for useblk in useblks:
                    results = []
                    self._trace_path(defblk, defblk, useblk, [], results, False)
                    for blks, hasloop in results:
                        logger.log(0, 'path -- ' + ', '.join([b.name for b in blks]))
                        logger.log(0, 'hasloop ' + str(hasloop))
                        self.liveouts[blks[0]].add((sym, hasloop))
                        if len(blks) > 1:
                            for b in blks[1:-1]:
                                self.liveins[b].add((sym, hasloop))
                                self.liveouts[b].add((sym, hasloop))
                            self.liveins[blks[-1]].add((sym, hasloop))
        scope.liveins = self.liveins
        scope.liveouts = self.liveouts
        #self.dump()


    def dump(self):
        logger.debug("::::: Live in :::::")
        for blk, syms in sorted(self.liveins.items()):
            logger.debug(blk.name)
            logger.debug('   ' + ', '.join([s.name+':'+str(hasloop) for s, hasloop in syms]))
        logger.debug("::::: Live out :::::")
        for blk, syms in sorted(self.liveouts.items()):
            logger.debug(blk.name)
            logger.debug('   ' + ', '.join([s.name+':'+str(hasloop) for s, hasloop in syms]))

    def _trace_path(self, start, frm, to, path, results, hasloop):
        if frm in path:
            return
        path.append(frm)
        if frm is to:
            results.append((list(path), hasloop))
            return True
        for succ in frm.succs:
            if start is succ:
                continue
            hasloop |= succ in frm.succs_loop
            self._trace_path(start, succ, to, path, results, hasloop)
        path.pop()
        return False
