import setuptools

setuptools.setup(
    name = 'polyphony',
    version = '0.1.4',
    packages = setuptools.find_packages(),
    author = "Hiroaki Kataoka",
    author_email = "kataoka@sinby.com",
    description = "Python based High Level Synthesis compiler",
    long_description=open('README.rst').read(),
    keywords = "HLS High Level Synthesis FPGA HDL Verilog VHDL EDA",
    license='MIT',
    scripts=['bin/polyphony'],
    url='https://github.com/ktok07b6/polyphony',
)
