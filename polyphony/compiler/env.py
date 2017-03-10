import logging


class Env(object):
    PHASE_1 = 1
    PHASE_2 = 2
    PHASE_3 = 3
    PHASE_4 = 4
    PHASE_GEN_HDL = 5

    def __init__(self):
        self.call_graph = None
        self.scopes = {}
        self.all_scopes = {}
        self.dev_debug_mode = False
        self.hdl_debug_mode = False
        self.compile_phase = 0
        self.logfiles = {}
        self.using_libs = set()
        self.memref_graph = None
        self.ctor_name = '__init__'
        self.self_name = 'self'
        self.callop_name = '__call__'
        self.scope_file_map = {}
        self.current_filename = None
        self.enable_ahdl_opt = False
        self.testbenches = []

    def set_current_filename(self, filename):
        self.current_filename = filename

    def append_scope(self, scope):
        self.scope_file_map[scope] = self.current_filename
        self.scopes[scope.name] = scope
        self.all_scopes[scope.name] = scope
        if self.dev_debug_mode and not scope.is_lib():
            logfile = logging.FileHandler('.tmp/debug_log.' + scope.name.replace('@', ''), 'w')
            self.logfiles[scope] = logfile

    def remove_scope(self, scope):
        del self.scopes[scope.name]

    def add_using_lib(self, lib):
        self.using_libs.add(lib)

    def append_testbench(self, testbench):
        self.testbenches.append(testbench)


env = Env()
