import inspect
from .scope import Scope
from .env import env
import logging


class Driver(object):
    def __init__(self, procs, scopes):
        self.procs = procs
        self.scopes = scopes[:]
        self.logger = logging.getLogger()  # root logger
        self.codes = {}

    def insert_scope(self, scope):
        self.scopes.append(scope)

    def remove_scope(self, scope):
        if scope in self.scopes:
            self.scopes.remove(scope)

    def start_logging(self, proc, scope):
        if env.dev_debug_mode and scope in env.logfiles:
            self.logger.addHandler(env.logfiles[scope])
        self.logger.debug('--------------------------')
        self.logger.debug(str(proc.__name__) + ':' + scope.name)

    def end_logging(self, proc, scope):
        if env.dev_debug_mode and scope in env.logfiles:
            self.logger.removeHandler(env.logfiles[scope])

    def run(self):
        while True:
            for i, proc in enumerate(self.procs):
                self.stage = i
                args, _, _, _ = inspect.getargspec(proc)
                Scope.reorder_scopes()
                self.scopes.sort(key=lambda s: s.order)
                scopes = self.scopes[:]

                if 'scope' not in args:
                    for s in scopes:
                        self.start_logging(proc, s)
                    proc(self)
                    for s in scopes:
                        self.end_logging(proc, s)
                else:
                    for s in reversed(scopes):
                        self.start_logging(proc, s)
                        proc(self, s)
                        self.end_logging(proc, s)
            else:
                break

    def set_result(self, scope, code):
        self.codes[scope] = code

    def result(self, scope):
        if scope in self.codes:
            return self.codes[scope]
        return None
