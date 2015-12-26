#!/bin/sh
rm out/test

basename=${1##*/}
echo "basename: $basename"

filename=${basename%.*}
echo "filename: $filename"

python3 __main__.py -d tmp -o $filename $1
FILES=`ls tmp/`
PATHS=`ls -d tmp/*`
echo $PATHS
iverilog -o out/test -s test $PATHS
for f in $FILES; do \
	cp tmp/$f out/
	rm tmp/$f
done
./out/test
