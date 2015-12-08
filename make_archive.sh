#!/bin/sh

PYTHON="/usr/bin/env python3"
zip --quiet polyphony *.py
echo "#!"$PYTHON > polyphony
cat polyphony.zip >> polyphony
rm polyphony.zip
chmod a+x polyphony