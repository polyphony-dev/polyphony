from polyphony import testbench

#'and' evaluation precedes 'or'
def expr10(a, b, c):
    x = a | b & c
    y = (a|b) & c
    z = a | (b&c)
    return (x != y) and (x==z)

@testbench
def test():
    assert True == expr10(0b1000, 0b1001, 0b0011)
    assert True == expr10(0b1000, 0b1111, 0b0111)
    assert True == expr10(0b1001, 0b1001, 0b1000)
