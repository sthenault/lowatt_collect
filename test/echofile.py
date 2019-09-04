#!/usr/bin/python

import sys
from os.path import join, dirname

output = sys.argv[1]
with open(output, 'a') as stream:
    stream.write(' '.join(sys.argv[2:]) + '\n')

# write index file like
index = join(dirname(output), '.index.json')
with open(index, 'w') as stream:
    stream.write('0')
