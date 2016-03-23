import logging

class Env:
    PHASE_1 = 1
    PHASE_2 = 2
    PHASE_3 = 3
    PHASE_4 = 4
    PHASE_GEN_HDL = 5

    def __init__(self):
        self.call_graph = None
        self.scopes = {}
        self.dev_debug_mode = False
        self.hdl_debug_mode = False
        self.compile_phase = 0
        self.logfiles = {}
        self.using_libs = set()
        self.memref_graph = None

    def append_scope(self, scope):
        self.scopes[scope.name] = scope
        if self.dev_debug_mode:
            logfile = logging.FileHandler('debug_log.' + scope.name.replace('@',''), 'w')
            self.logfiles[scope] = logfile

    def remove_scope(self, scope):
        del self.scopes[scope.name]

    def dump(self):
        for s in self.scopes:
            logger.debug(str(s))

    def add_using_lib(self, lib):
        self.using_libs.add(lib)


env = Env()
