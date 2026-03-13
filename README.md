[![Test Suite](https://github.com/ktok07b6/polyphony/actions/workflows/test.yml/badge.svg?branch=devel)](https://github.com/ktok07b6/polyphony/actions/workflows/test.yml)
[![PyPI](https://badge.fury.io/py/polyphony.svg)](https://badge.fury.io/py/polyphony)
[![Python](https://img.shields.io/badge/python-%3E%3D3.12-blue)](https://github.com/ktok07b6/polyphony)
[![License](https://img.shields.io/github/license/ktok07b6/polyphony)](https://github.com/ktok07b6/polyphony/blob/main/LICENSE)

# polyphony

Polyphony is a Python-based High-Level Synthesis (HLS) compiler that generates synthesizable Verilog HDL from a Python subset.

## Requirements

- Python >= 3.12
- Icarus Verilog (for HDL simulation)

## Installation

```bash
pip install polyphony
```

## Usage

```
polyphony [-h] [-o FILE] [-d DIR] [-c CONFIG] [-v] [-D] [-hd] [-q]
          [-vd] [-vm] [-op PREFIX] [-t TARGETS [TARGETS ...]] [-V]
          source
```

| Option | Description |
|--------|-------------|
| `-o FILE, --output FILE` | output filename (default is "polyphony_out") |
| `-d DIR, --dir DIR` | output directory |
| `-c CONFIG, --config CONFIG` | set configuration (JSON literal or file) |
| `-v, --verbose` | verbose output |
| `-D, --debug` | enable debug mode |
| `-hd, --hdl_debug` | enable HDL debug mode |
| `-q, --quiet` | suppress warning/error messages |
| `-vd, --verilog_dump` | output VCD file in testbench |
| `-vm, --verilog_monitor` | enable $monitor in testbench |
| `-V, --version` | print the Polyphony version number |

## Examples

See [tests](https://github.com/ktok07b6/polyphony/tree/main/tests)

## License

MIT License. See [LICENSE](LICENSE) for details.
