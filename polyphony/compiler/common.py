import traceback
import logging
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


src_text = []
def read_source(filename):
    assert filename
    push_file_name(filename)
    f = open(filename, 'r')
    source_lines = f.readlines()
    f.close()
    set_src_text(source_lines)
    source = ''.join(source_lines)
    return source

def set_src_text(srcs):
    global src_text
    src_text = srcs
    logger.debug(src_text)

def get_src_text(lineno):
    assert lineno > 0
    return src_text[lineno-1]

filenames = []
def current_file_name():
    global filenames
    assert filenames
    return filenames[-1]

def push_file_name(filename):
    global filenames
    filenames.append(filename)

def pop_file_name():
    global filenames
    filenames.pop()

def error_info(lineno):
    return '{}\n{}:{}'.format(current_file_name(), lineno, get_src_text(lineno))

