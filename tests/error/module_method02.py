#Calling append_worker method can only at the constructor
from polyphony import module


def w():
    pass


@module
class module_method02:
    def __init__(self):
        pass


m = module_method02()
m.append_worker(w)
