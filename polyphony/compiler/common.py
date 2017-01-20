import traceback
import logging
from .env import env
logger = logging.getLogger()

INT_WIDTH = 32

def accepts(*types):
    def check_accepts(f):
        assert len(types) == f.func_code.co_argcount
        def new_f(*args, **kwds):
            for (a, t) in zip(args, types):
                assert isinstance(a, t), \
                       "arg %r does not match %s" % (a,t)
            return f(*args, **kwds)
        new_f.func_name = f.func_name
        return new_f
    return check_accepts

def funclog(func):
    def inner(*args, **kwargs):
        logger.debug("LOG:", func.__name__)
        ret = func(*args, **kwargs)
        return ret       
    return inner


src_texts = {}
def read_source(filename):
    assert filename
    env.set_current_filename(filename)
    f = open(filename, 'r')
    source_lines = f.readlines()
    f.close()
    src_texts[filename] = source_lines
    source = ''.join(source_lines)
    return source

def get_src_text(scope, lineno):
    assert scope in env.scope_file_map
    filename = env.scope_file_map[scope]
    assert lineno > 0
    return src_texts[filename][lineno-1]

def error_info(scope, lineno):
    assert scope in env.scope_file_map
    filename = env.scope_file_map[scope]
    return '{}\n{}:{}'.format(filename, lineno, get_src_text(scope, lineno))

