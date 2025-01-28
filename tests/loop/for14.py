from polyphony import testbench

def func(xs:list, ys:list):
    sum_x = 0
    for x in xs:
        sum_x += x
    sum_y = 0
    for y in ys:
        sum_y += y

    return sum_x + sum_y


def for14(a0, a1, a2, a3, a4, a5):
    return func([a0, a1, a2], [a3, a4, a5])


@testbench
def test():
    assert 1+2+3+4+5 == for14(0, 1, 2, 3, 4, 5)
    assert 5+6+7+8+9+10 == for14(5, 6, 7, 8, 9, 10)
