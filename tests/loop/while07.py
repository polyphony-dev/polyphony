from polyphony import testbench

shift_n = 8


def abs(x):
    if x < 0:
        return -x
    else:
        return x


def i_square(x):
    return x * x


def i_while(x):
    epsilon = 1
    new_x = x << shift_n
    guess = new_x >> 1
    old_guess = 0
    while (abs(i_square(guess) - new_x)) > epsilon:
        if old_guess == guess:
            break
        old_guess = guess
        guess = guess - 10

    return guess


@testbench
def test():
    x = 25
    result = i_while(x)
    assert result == 80


test()
