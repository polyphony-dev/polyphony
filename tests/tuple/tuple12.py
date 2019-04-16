from polyphony import testbench
from polyphony.typing import Tuple, List, int8


def f(x, y) -> Tuple[int8]:
    return x, y


def tuple12(xs:list, ys:list, i, j):
    ys[j], xs[i] = f(xs[i], ys[j])


@testbench
def test():
    xs:List[int8] = [1, 2, 3, 4]
    ys:List[int8] = [5, 6, 7, 8]
    tuple12(xs, ys, 0, 1)
    assert xs[0] == 6 and ys[1] == 1

    tuple12(ys, xs, 0, 2)
    assert xs[2] == 5 and ys[0] == 3


test()
