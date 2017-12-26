from polyphony import testbench

a = 0
b = a
c = b

if b:
    gs0 = [1, 2, 3]
else:
    gs0 = [4, 5, 6]

if c:
    gs = gs0
else:
    gs = gs0


def global06():
    sum = 0
    for g in gs:
        sum += g
    return sum

@testbench
def test():
    assert 15 == global06()

test()
