﻿from __future__ import annotations
from typing import TYPE_CHECKING
import logging
if TYPE_CHECKING:
    from ..ir.scope import Scope
    from ..ahdl.hdlscope import HDLScope


type ScopeDict = dict[str, Scope]

class Config(object):
    default_int_width = 32
    main_clock_frequency = 100000000
    reset_activation_signal = 1
    enable_pure = False
    perfect_inlining = False

    def __str__(self):
        d = {}
        for k in Config.__dict__:
            if k.startswith('__'):
                continue
            d[k] = Config.__dict__[k]
        d.update(self.__dict__)
        return str(d)


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
    debug_output_dir = '.tmp'
    ctor_name = '__init__'
    self_name = 'self'
    callop_name = '__call__'
    enable_ahdl_opt = True
    global_scope_name = '@top'
    enable_hyperblock = True
    verbose_level = 0
    quiet_level = 0
    enable_verilog_monitor = False
    enable_verilog_dump = False
    sleep_sentinel_thredhold = 10

    def __init__(self):
        self.call_graph = None
        self.depend_graph = None
        self.scopes: ScopeDict = {}
        self.all_scopes: ScopeDict = {}
        self.compile_phase = 0
        self.logfiles = {}
        self.scope_file_map = {}
        self.current_filename = None
        self.testbenches = []
        self.config = Config()
        self.runtime_info = None
        self.outermost_scope_stack = []
        self.scope2hdlscope: dict[Scope, HDLScope] = {}
        self.scope2output_hdlscope: dict[Scope, HDLScope] = {}
        self.targets = []
        self.root_dir = ''

    def load_config(self, config):
        for key, v in config.items():
            setattr(self.config, key, v)

    def set_current_filename(self, filename):
        self.current_filename = filename

    def append_scope(self, scope: Scope):
        self.scope_file_map[scope] = self.current_filename
        self.scopes[scope.name] = scope
        self.all_scopes[scope.name] = scope

    def destroy(self):
        for logfile in self.logfiles.values():
            logfile.close()

    def remove_scope(self, scope: Scope):
        del self.scopes[scope.name]

    def append_testbench(self, testbench):
        self.testbenches.append(testbench)

    def push_outermost_scope(self, scope: Scope):
        self.outermost_scope_stack.append(scope)

    def pop_outermost_scope(self):
        self.outermost_scope_stack.pop()

    def outermost_scope(self):
        return self.outermost_scope_stack[-1]

    def append_hdlscope(self, hdlscope: HDLScope):
        self.append_hdlscope_core(hdlscope, self.scope2hdlscope)

    def append_output_hdlscope(self, hdlscope: HDLScope):
        self.append_hdlscope_core(hdlscope, self.scope2output_hdlscope)

    def append_hdlscope_core(self, hdlscope: HDLScope, dict):
        dict[hdlscope.scope] = hdlscope
        if hdlscope.scope.is_module():
            for w in hdlscope.scope.workers:
                dict[w] = hdlscope
            ctor = hdlscope.scope.find_ctor()
            if ctor:
                dict[ctor] = hdlscope

    def hdlscope(self, scope: Scope) -> HDLScope:
        assert scope in self.scope2hdlscope
        return self.scope2hdlscope[scope]

    def output_hdlscope(self, scope: Scope) -> HDLScope | None:
        if scope in self.scope2output_hdlscope:
            return self.scope2output_hdlscope[scope]
        return None

    def process_log_handler(self, stage, proc):
        logname = f'{self.debug_output_dir}/{stage}_{proc.__name__}.log'
        if logname not in self.logfiles:
            self.logfiles[logname] = logging.FileHandler(logname, 'w')
        return self.logfiles[logname]

    def scope_log_handler(self, scope: Scope):
        scope_log = scope.name.replace('@', '')
        logname = f'{self.debug_output_dir}/{scope_log}.log'
        if logname not in self.logfiles:
            self.logfiles[logname] = logging.FileHandler(logname, 'w')
        return self.logfiles[logname]

env = Env()
