#Sequence capacity is overflowing
from polyphony import testbench
from polyphony.typing import List, bit


def seq_capacity01(xs:List[bit][4]):
    return xs[7]


@testbench
def test():
    data = [0, 1, 1, 0, 1]  # type: List[bit][4]
    seq_capacity01(data)


test()
