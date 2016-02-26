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
echo $PATHS
iverilog -o out/test -s test $PATHS

if [ $? -ne 0 ]; then
    echo Something Error has occured.
    exit 1
fi

for f in $FILES; do \
	cp tmp/$f out/
	rm tmp/$f
done
./out/test
