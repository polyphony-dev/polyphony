from polyphony import testbench

def for14(xs:list, ys:list):
    sum_x = 0
    for x in xs:
        sum_x += x
        
    sum_y = 0
    for y in ys:
        sum_y += y

    return sum_x + sum_y

@testbench
def test():
    assert 1+2+3+4+5 == for14([0, 1, 2], [3, 4, 5])
    assert 5+6+7+8+9+10 == for14([5, 6, 7], [8, 9, 10])
test()
