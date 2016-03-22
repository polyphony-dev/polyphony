#!/bin/sh

if [ -f out/test ]; then
    rm out/test
fi

which iverilog 2> /dev/null
if [ $? -ne 0 ]; then
    echo You need iverilog.
    exit 1
fi

 
basename=${1##*/}
echo "basename: $basename"

filename=${basename%.*}
echo "filename: $filename"

python3 -m polyphony.compiler -d tmp -o $filename $1

if [ $? -ne 0 ]; then
    echo Something Error has occured.
    exit 1
fi

FILES=`ls tmp/`
PATHS=`ls -d tmp/*`

iverilog -o out/test -s test $PATHS
VERILOG_ERROR=0
if [ $? -ne 0 ]; then
	let VERILOG_ERROR=1
fi

echo $PATHS
for f in $FILES; do \
	cp tmp/$f out/
	rm tmp/$f
done

if [ $VERILOG_ERROR -eq 1 ]; then
    echo Something Error has occured.
    exit 1
fi

./out/test
if [ $? -ne 0 ]; then
	let VERILOG_ERROR=1
fi
if [ $VERILOG_ERROR -eq 1 ]; then
    echo Something Error has occured.
    exit 1
fi
