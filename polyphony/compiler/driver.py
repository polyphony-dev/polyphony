import inspect
from collections import defaultdict, namedtuple
from .scope import Scope
from .env import env
import logging
import pdb

class Driver:
    def __init__(self, procs, scopes):
        self.procs = procs
        self.unprocessed_scopes = [None] * len(procs)
        for i in range(len(procs)):
            self.unprocessed_scopes[i] = scopes[:]
        self.updated = False
        self.logger = logging.getLogger() #root logger
        self.codes = {}
        self.insert_reserved_scopes = []

    def insert_scope(self, scope):
        self.insert_reserved_scopes.append(scope)
        self.updated = True

    def remove_scope(self, scope):
        for scopes in self.unprocessed_scopes:
            if scope in scopes: scopes.remove(scope)

    def start_logging(self, proc, scope):
        if env.dev_debug_mode:
            self.logger.addHandler(env.logfiles[scope])
        self.logger.debug('--------------------------')
        self.logger.debug(str(proc.__name__) + ':' + scope.name)
    def end_logging(self, proc, scope):
        if env.dev_debug_mode:
            self.logger.removeHandler(env.logfiles[scope])

    def run(self):
        while True:
            for i, proc in enumerate(self.procs):
                self.stage = i
                args, _, _, _ = inspect.getargspec(proc)
                Scope.reorder_scopes()
                self.unprocessed_scopes[i].sort(key=lambda s: s.order)
                scopes = self.unprocessed_scopes[i][:]

                if 'scope' not in args:
                    for s in scopes:
                        self.start_logging(proc, s)
                    proc(self)
                    for s in scopes:
                        self.end_logging(proc, s)
                        if s in self.unprocessed_scopes[i]:
                            self.unprocessed_scopes[i].remove(s)
                else:
                    for s in reversed(scopes):
                        self.start_logging(proc, s)
                        proc(self, s)
                        self.end_logging(proc, s)
                        if s in self.unprocessed_scopes[i]:
                            self.unprocessed_scopes[i].remove(s)
                if self.updated:
                    for s in self.insert_reserved_scopes:
                        for i in range(len(self.procs)):
                          self.unprocessed_scopes[i].append(s)
                    self.updated = False
                    self.insert_reserved_scopes = []
                    break
            else:
                break

    def set_result(self, scope, code):
        self.codes[scope] = code

    def result(self, scope):
        if scope in self.codes:
            return self.codes[scope]
        return None

class TestScope:
    def __init__(self, name, order):
        self.name = name
        self.order = order
    
if __name__ == '__main__':
    def proc_1(driver, scope):
        print('proc1 ' + scope.name)
    def proc_2(driver, scope):
        print('proc2 ' + scope.name)
        if scope.name == 's2':
            driver.insert_scope(TestScope('s2+', 2))
    def proc_3(driver, scope):
        print('proc3 ' + scope.name)
    procs = [proc_1, proc_2, proc_3]
    scopes = [TestScope('s1', 1), TestScope('s2', 2), TestScope('s3',3)]
    driver = Driver(procs, scopes)
    driver.run()
