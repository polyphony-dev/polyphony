from polyphony import testbench


class C:
    i = 1234

    def __init__(self):
        self.v1 = self.i
        self.v2 = C.i


def classfield07():
    return C.i == C().v1 == C().v2


@testbench
def test():
    assert classfield07()
