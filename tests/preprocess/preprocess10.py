from polyphony import preprocess as pre
from polyphony import testbench


@pre
def save_test_data(file_name, data):
    with open(file_name, 'wb') as f:
        for d in data:
            f.write(d.to_bytes(1, 'little'))


@pre
def load_test_data(file_name):
    with open(file_name, 'rb') as f:
        return list(bytearray(f.read()))


def preprocess10(data):
    sum = 0
    for d in data:
        sum += d
    return sum


@testbench
def test():
    save_test_data('.tmp/test_data.bin', [0x11, 0x22, 0x33, 0x44, 0x55])

    data = load_test_data('.tmp/test_data.bin')
    assert 0x11 + 0x22 + 0x33 + 0x44 + 0x55 == preprocess10(data)


test()
