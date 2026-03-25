import os

RUNTIME_H = os.path.join(
    os.path.dirname(__file__),
    '../../../../polyphony/compiler/target/csim/runtime_template.h',
)


def test_runtime_template_exists():
    assert os.path.isfile(RUNTIME_H)


def test_runtime_template_has_mask():
    with open(RUNTIME_H) as f:
        src = f.read()
    assert 'mask' in src
    assert 'int64_t' in src
