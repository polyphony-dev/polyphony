#'data' is incompatible type as a parameter of seq_capacity02()
from polyphony import testbench
from polyphony.typing import List, bit


def seq_capacity02(xs:List[bit][8]):
    return xs[7]


@testbench
def test():
    data = [0, 1, 1, 0]  # type: List[bit][4]
    seq_capacity02(data)


test()
