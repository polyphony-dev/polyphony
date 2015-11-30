#!/bin/sh

if [ $# -gt 0 ]; then
TEST_DIRS=$1
else
TEST_DIRS="expr if loop return list scope func parallel testbench"
fi

for d in $TEST_DIRS; do \
	FILES=`ls tests/$d/*.py`
	for f in $FILES; do \
		echo $f
		./simu.sh $f | grep '^ASSERTION'
	done
done

rm debug_log*
