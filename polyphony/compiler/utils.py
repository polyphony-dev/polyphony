def is_a(inst, cls):
    if isinstance(cls, list) or isinstance(cls, tuple):
        for c in cls:
            if isinstance(inst, c):
                return True
        return False
    else:
        return isinstance(inst, cls)

def replace_item(lst, old, new):
    if isinstance(old, list) or isinstance(old, tuple):
        for o in old:
            replace_item(lst, o, new)
    else:
        for i, s in enumerate(lst):
            if s is old:
                lst[i] = new
                break

def remove_from_list(lst, removes):
    for r in removes:
        if r in lst:
            lst.remove(r)

def unique(lst):
    return sorted(list(set(lst)))


