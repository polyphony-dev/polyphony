import logging
from .env import env
logger = logging.getLogger()


src_texts = {}


def read_source(filename):
    assert filename
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
    return src_texts[filename][lineno - 1]


def error_info(scope, lineno):
    assert scope in env.scope_file_map
    filename = env.scope_file_map[scope]
    return '{}\n{}:{}'.format(filename, lineno, get_src_text(scope, lineno))


class CompileError(Exception):
    pass


def fail(ir, err_id, args=None):
    print(error_info(ir.block.scope, ir.lineno))
    if args:
        msg = str(err_id).format(*args)
    else:
        msg = str(err_id)
    raise CompileError(msg)


class Tagged(object):
    __slots__ = ['tags']

    def __init__(self, tags):
        if isinstance(tags, list):
            tags = set(tags)
        elif tags is None:
            tags = set()
        assert isinstance(tags, set)
        self.tags = tags
        assert self.tags.issubset(self.TAGS)

    def __getattr__(self, name):
        if name.startswith('is_'):
            tag = name[3:]
            if tag not in self.TAGS:
                raise AttributeError(name)
            return lambda: tag in self.tags
        else:
            raise AttributeError(name)

    def add_tag(self, tag):
        if isinstance(tag, set):
            self.tags = self.tags | tag
        elif isinstance(tag, list):
            self.tags = self.tags | set(tag)
        else:
            self.tags.add(tag)
        assert self.tags.issubset(self.TAGS)

    def del_tag(self, tag):
        if isinstance(tag, set):
            self.tags = self.tags - tag
        elif isinstance(tag, list):
            self.tags = self.tags - set(tag)
        else:
            self.tags.discard(tag)
