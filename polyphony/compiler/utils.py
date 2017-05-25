def is_a(inst, cls):
    if isinstance(cls, list) or isinstance(cls, tuple):
        for c in cls:
            if isinstance(inst, c):
                return True
        return False
    else:
        return isinstance(inst, cls)


def find_only_one_in(typ, seq):
    it = None
    for item in seq:
        if item.is_a(typ):
            assert it is None
            it = item
    return it


def replace_item(lst, old, new, all=False):
    if isinstance(old, list) or isinstance(old, tuple):
        for o in old:
            replace_item(lst, o, new)
    else:
        for i, s in enumerate(lst):
            if s is old:
                lst[i] = new
                if not all:
                    break


def remove_from_list(lst, removes):
    for r in removes:
        if r in lst:
            lst.remove(r)


def remove_except_one(lst, target):
    for idx, item in enumerate(lst[:]):
        if item is target:
            rest = [r for r in lst[idx + 1:] if r is not target]
            return lst[:idx + 1] + rest
    return lst


def unique(lst):
    return sorted(list(set(lst)))


_36chars = [chr(ord('0') + i) for i in range(10)] + [chr(ord('a') + i) for i in range(26)]


def id2str(idnum):
    s = ''
    tmp = idnum
    if tmp == 0:
        return '0'
    while tmp:
        i = tmp % 36
        tmp = tmp // 36
        s += _36chars[i]
    return s[::-1]

