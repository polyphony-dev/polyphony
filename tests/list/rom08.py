from polyphony import testbench


def rom08(zs1, zs2):
    rom0 = [1, 2, 3, 4, 5]
    rom1 = [6, 7, 8, 9, 10]
    xs = rom0
    ys = rom1
    for i in range(len(xs)):
        zs1[i] = xs[i]
        zs2[i] = ys[i]

        tmp = xs
        xs = ys
        ys = tmp


@testbench
def test():
    zs1 = [0] * 5
    zs2 = [0] * 5
    rom08(zs1, zs2)
    assert 1 == zs1[0]
    assert 7 == zs1[1]
    assert 3 == zs1[2]
    assert 9 == zs1[3]
    assert 5 == zs1[4]

    assert 6 == zs2[0]
    assert 2 == zs2[1]
    assert 8 == zs2[2]
    assert 4 == zs2[3]
    assert 10 == zs2[4]


test()
