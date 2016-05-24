#!/bin/sh

if [ $# -gt 0 ]; then
TEST_DIRS=$1
else
TEST_DIRS="expr if loop return list scope func parallel testbench class"
fi

if [ ! -d out ]; then
    mkdir out
fi

if [ ! -d tmp ]; then
    mkdir tmp
fi


for d in $TEST_DIRS; do \
	FILES=`ls tests/$d/*.py`
	for f in $FILES; do \
		echo $f
		./simu.sh $f 2> /dev/stdout | grep '^ASSERTION\|Error\|error'
	done
done

rm debug_log*
