from polyphony import testbench


def long_elif_chain(x):
    if x == 0:
        return 0
    elif x == 1:
        return 4
    elif x == 2:
        return 7
    elif x == 3:
        return 10
    elif x == 4:
        return 13
    elif x == 5:
        return 16
    elif x == 6:
        return 19
    elif x == 7:
        return 22
    elif x == 8:
        return 25
    elif x == 9:
        return 28
    elif x == 10:
        return 31
    elif x == 11:
        return 34
    elif x == 12:
        return 37
    elif x == 13:
        return 40
    elif x == 14:
        return 43
    elif x == 15:
        return 46
    elif x == 16:
        return 49
    elif x == 17:
        return 52
    elif x == 18:
        return 55
    elif x == 19:
        return 58
    elif x == 20:
        return 61
    elif x == 21:
        return 64
    elif x == 22:
        return 67
    elif x == 23:
        return 70
    elif x == 24:
        return 73
    elif x == 25:
        return 76
    elif x == 26:
        return 79
    elif x == 27:
        return 82
    elif x == 28:
        return 85
    elif x == 29:
        return 88
    elif x == 30:
        return 91
    elif x == 31:
        return 94
    elif x == 32:
        return 97
    elif x == 33:
        return 100
    elif x == 34:
        return 103
    elif x == 35:
        return 106
    elif x == 36:
        return 109
    elif x == 37:
        return 112
    elif x == 38:
        return 115
    elif x == 39:
        return 118
    elif x == 40:
        return 121
    elif x == 41:
        return 124
    elif x == 42:
        return 127
    elif x == 43:
        return 130
    elif x == 44:
        return 133
    elif x == 45:
        return 136
    elif x == 46:
        return 139
    elif x == 47:
        return 142
    elif x == 48:
        return 145
    elif x == 49:
        return 148
    elif x == 50:
        return 151
    elif x == 51:
        return 154
    elif x == 52:
        return 157
    elif x == 53:
        return 160
    elif x == 54:
        return 163
    elif x == 55:
        return 166
    elif x == 56:
        return 169
    elif x == 57:
        return 172
    elif x == 58:
        return 175
    elif x == 59:
        return 178
    elif x == 60:
        return 181
    elif x == 61:
        return 184
    elif x == 62:
        return 187
    else:
        return -1


@testbench
def test():
    assert 0 == long_elif_chain(0)
    assert 4 == long_elif_chain(1)
    assert 7 == long_elif_chain(2)
    assert 10 == long_elif_chain(3)
    assert 13 == long_elif_chain(4)
    assert 16 == long_elif_chain(5)
    assert 19 == long_elif_chain(6)
    assert 22 == long_elif_chain(7)
    assert 25 == long_elif_chain(8)
    assert 28 == long_elif_chain(9)
    assert 31 == long_elif_chain(10)
    assert 34 == long_elif_chain(11)
    assert 37 == long_elif_chain(12)
    assert 40 == long_elif_chain(13)
    assert 43 == long_elif_chain(14)
    assert 46 == long_elif_chain(15)
    assert 49 == long_elif_chain(16)
    assert 52 == long_elif_chain(17)
    assert 55 == long_elif_chain(18)
    assert 58 == long_elif_chain(19)
    assert 61 == long_elif_chain(20)
    assert 64 == long_elif_chain(21)
    assert 67 == long_elif_chain(22)
    assert 70 == long_elif_chain(23)
    assert 73 == long_elif_chain(24)
    assert 76 == long_elif_chain(25)
    assert 79 == long_elif_chain(26)
    assert 82 == long_elif_chain(27)
    assert 85 == long_elif_chain(28)
    assert 88 == long_elif_chain(29)
    assert 91 == long_elif_chain(30)
    assert 94 == long_elif_chain(31)
    assert 97 == long_elif_chain(32)
    assert 100 == long_elif_chain(33)
    assert 103 == long_elif_chain(34)
    assert 106 == long_elif_chain(35)
    assert 109 == long_elif_chain(36)
    assert 112 == long_elif_chain(37)
    assert 115 == long_elif_chain(38)
    assert 118 == long_elif_chain(39)
    assert 121 == long_elif_chain(40)
    assert 124 == long_elif_chain(41)
    assert 127 == long_elif_chain(42)
    assert 130 == long_elif_chain(43)
    assert 133 == long_elif_chain(44)
    assert 136 == long_elif_chain(45)
    assert 139 == long_elif_chain(46)
    assert 142 == long_elif_chain(47)
    assert 145 == long_elif_chain(48)
    assert 148 == long_elif_chain(49)
    assert 151 == long_elif_chain(50)
    assert 154 == long_elif_chain(51)
    assert 157 == long_elif_chain(52)
    assert 160 == long_elif_chain(53)
    assert 163 == long_elif_chain(54)
    assert 166 == long_elif_chain(55)
    assert 169 == long_elif_chain(56)
    assert 172 == long_elif_chain(57)
    assert 175 == long_elif_chain(58)
    assert 178 == long_elif_chain(59)
    assert 181 == long_elif_chain(60)
    assert 184 == long_elif_chain(61)
    assert 187 == long_elif_chain(62)
    assert -1 == long_elif_chain(63)
