from polyphony import testbench


def rom09(p, q, zs1, zs2):
    rom0 = [1, 2, 3, 4, 5]
    rom1 = [6, 7, 8, 9, 10]
    if p:
        xs = rom0
        ys = rom1
    else:
        xs = rom1
        ys = rom0

    for i in range(len(xs)):
        zs1[i] += xs[i]
    for i in range(len(ys)):
        zs2[i] += ys[i]

    if q:
        xxs = xs
        yys = ys
    else:
        xxs = ys
        yys = xs

    for i in range(len(xxs)):
        zs1[i] += xxs[i]
    for i in range(len(yys)):
        zs2[i] += yys[i]


@testbench
def test():
    zs1 = [0] * 5
    zs2 = [0] * 5
    rom09(True, True, zs1, zs2)
    assert 2 == zs1[0]
    assert 4 == zs1[1]
    assert 6 == zs1[2]
    assert 8 == zs1[3]
    assert 10 == zs1[4]

    assert 12 == zs2[0]
    assert 14 == zs2[1]
    assert 16 == zs2[2]
    assert 18 == zs2[3]
    assert 20 == zs2[4]

    zs1 = [0] * 5
    zs2 = [0] * 5
    rom09(True, False, zs1, zs2)
    assert 7 == zs1[0]
    assert 9 == zs1[1]
    assert 11 == zs1[2]
    assert 13 == zs1[3]
    assert 15 == zs1[4]

    assert 7 == zs2[0]
    assert 9 == zs2[1]
    assert 11 == zs2[2]
    assert 13 == zs2[3]
    assert 15 == zs2[4]


test()
