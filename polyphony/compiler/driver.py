import inspect
import sys
from .ir.scope import Scope
from .common.env import env
import logging


class Driver(object):
    def __init__(self, procs, scopes, options, stage_offset=0):
        self.procs = procs
        self._scopes = scopes[:]
        self.disable_scopes = []
        self.options = options
        self.stage_offset = stage_offset
        self.logger = logging.getLogger()  # root logger
        self._scope_filter = None
        self._order_func = lambda scopes: scopes

    @property
    def current_scopes(self):
        scopes = self._scopes[:]
        if self._scope_filter:
            scopes = list(filter(self._scope_filter, scopes))
        return self._order_func(scopes)

    def insert_scope(self, scope):
        self.logger.debug(f'Driver.insert_scope {scope.name}')
        self._scopes.append(scope)

    def remove_scope(self, scope):
        self.logger.debug(f'Driver.remove_scope {scope.name}')
        if scope in self._scopes:
            self._scopes.remove(scope)
        if scope in self.disable_scopes:
            self.disable_scopes.remove(scope)

    def enable_scope(self, scope):
        if scope in self.disable_scopes:
            self._scopes.append(scope)
            self.disable_scopes.remove(scope)
        else:
            if scope not in self._scopes:
                print(scope.name)
            assert scope in self._scopes

    def disable_scope(self, scope):
        if scope in self._scopes:
            self.disable_scopes.append(scope)
            self._scopes.remove(scope)
        else:
            assert scope in self.disable_scopes

    def disable_all(self):
        for scope in self._scopes[:]:
            self.disable_scopes.append(scope)
            self._scopes.remove(scope)

    def set_filter(self, filter):
        self._scope_filter = filter

    def set_order_func(self, func):
        self._order_func = func

    def get_scopes(self, bottom_up=True, with_global=False, with_class=False, with_lib=False):
        scopes = Scope.get_scopes(bottom_up, with_global, with_class, with_lib)
        return [s for s in scopes if s in self._scopes]

    def all_scopes(self):
        return self._scopes + self.disable_scopes

    def start_logging_for_scope(self, scope, stage, proc):
        if env.dev_debug_mode:
            if not scope.is_lib() and not scope.is_inlinelib():
                self.logger.addHandler(env.scope_log_handler(scope))

    def start_logging_for_proc(self, stage, proc):
        if env.dev_debug_mode:
            self.logger.addHandler(env.process_log_handler(stage, proc))

    def end_logging_for_scope(self, scope):
        if env.dev_debug_mode:
            if not scope.is_lib() and not scope.is_inlinelib():
                self.logger.removeHandler(env.scope_log_handler(scope))

    def end_logging_for_proc(self, stage, proc):
        if env.dev_debug_mode:
            self.logger.removeHandler(env.process_log_handler(stage, proc))

    def log_scope_names(self, scopes):
        self.logger.debug('scopes:')
        for s in scopes:
            self.logger.debug(f'    {s.name}')

    def run(self, title):
        while True:
            for i, proc in enumerate(self.procs):
                if env.dev_debug_mode:
                    print_progress(title, proc, (i + 1) * 100 // len(self.procs))
                stage = self.stage_offset + i
                scopes = self.current_scopes
                if 'scope' not in inspect.signature(proc).parameters:
                    self.start_logging_for_proc(stage, proc)
                    self.log_scope_names(scopes)
                    # dump scopes
                    self.logger.debug('\ndump scopes:')
                    for s in scopes:
                        self.logger.debug(str(s))

                    self.logger.debug(f'{stage}-{proc.__name__}')
                    proc(self)
                    # dump scopes
                    self.logger.debug('\ndump scopes:')
                    for s in self.current_scopes:
                        self.logger.debug(str(s))
                    self.end_logging_for_proc(stage, proc)
                else:
                    self.start_logging_for_proc(stage, proc)
                    self.log_scope_names(scopes)
                    for s in scopes:
                        self.start_logging_for_scope(s, stage, proc)
                        self.logger.debug(f'{stage}-{proc.__name__}: {s.name}')
                        proc(self, s)
                        self.end_logging_for_scope(s)
                    # dump scopes
                    self.logger.debug('\ndump scopes:')
                    for s in self.current_scopes:
                        self.logger.debug(str(s))
                    self.end_logging_for_proc(stage, proc)
            else:
                break


def print_progress(title, proc, percent):
    i = percent // 4
    sys.stdout.write('\r')
    sys.stdout.write('{:<11}: [{:<25}] {}% ... {:<40}'.format(title, '=' * i, percent, proc.__name__))
    sys.stdout.flush()
    if percent == 100:
        print('')
