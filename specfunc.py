from copy import deepcopy

class SpecializedFunctionMaker:
    def __init__(self):
        pass

    def process(self, scope):
        return []
        self.scope = scope
        for meminfo in scope.meminfos:
            # this meminfo has multiple source mems
            for src_mem in meminfo.src_mems[1:]:
                new_scope = self.clone_scope(scope, src_mem.sym.name)
                new_scope.name
            meminfo.src_mems = [meminfo.src_mems[0]]

        return []

