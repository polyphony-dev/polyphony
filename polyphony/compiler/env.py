import logging


class Config(object):
    default_int_width = 32
    main_clock_frequency = 100000000
    reset_activation_signal = 1
    internal_ram_threshold_size = 512  # width * length


class Env(object):
    PHASE_1 = 1
    PHASE_2 = 2
    PHASE_3 = 3
    PHASE_4 = 4
    PHASE_5 = 5
    PHASE_GEN_HDL = 6

    QUIET_WARN = 1
    QUIET_ERROR = 2

    dev_debug_mode = False
    hdl_debug_mode = False
    ctor_name = '__init__'
    self_name = 'self'
    callop_name = '__call__'
    enable_ahdl_opt = True
    global_scope_name = '@top'
    enable_pure = True
    enable_hyperblock = False
    verbose_level = 0
    quiet_level = 0

    def __init__(self):
        self.call_graph = None
        self.scopes = {}
        self.all_scopes = {}
        self.compile_phase = 0
        self.logfiles = {}
        self.using_libs = set()
        self.memref_graph = None
        self.scope_file_map = {}
        self.current_filename = None
        self.testbenches = []
        self.config = Config()
        self.runtime_info = None
        self.outermost_scope_stack = []

    def set_current_filename(self, filename):
        self.current_filename = filename

    def append_scope(self, scope):
        self.scope_file_map[scope] = self.current_filename
        self.scopes[scope.name] = scope
        self.all_scopes[scope.name] = scope
        if self.dev_debug_mode and (not scope.is_lib() and not scope.is_inlinelib()):
            logfile = logging.FileHandler('.tmp/debug_log.' + scope.name.replace('@', ''), 'w')
            self.logfiles[scope] = logfile

    def remove_scope(self, scope):
        del self.scopes[scope.name]

    def add_using_lib(self, lib):
        self.using_libs.add(lib)

    def append_testbench(self, testbench):
        self.testbenches.append(testbench)

    def push_outermost_scope(self, scope):
        self.outermost_scope_stack.append(scope)

    def pop_outermost_scope(self):
        self.outermost_scope_stack.pop()

    def outermost_scope(self):
        return self.outermost_scope_stack[-1]


env = Env()
