import logging

class Env:
    def __init__(self):
        self.call_graph = None
        self.scopes = {}
        self.dev_debug_mode = True
        self.hdl_debug_mode = False
        self.compile_phase = ''
        self.logfiles = {}

    def append_scope(self, scope):
        self.scopes[scope.name] = scope
        logfile = logging.FileHandler('debug_log.' + scope.name.replace('@',''), 'w')
        self.logfiles[scope] = logfile

    def dump(self):
        for s in self.scopes:
            logger.debug(str(s))

    def serialize_function_tree(self, contain_global=False):
        functions = []
        top = self.scopes['@top']
        self._serialize_function_tree_rec(top, functions)
        if not contain_global:
            functions.remove(top)
        return functions

    def _serialize_function_tree_rec(self, f, functions):
        if not f.children:
            functions.append(f)
        else:
            for c in f.children:
                self._serialize_function_tree_rec(c, functions)
            functions.append(f)

env = Env()
