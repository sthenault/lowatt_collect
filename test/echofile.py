#!/usr/bin/python

import sys
output = sys.argv[1]
with open(output, 'a') as stream:
    stream.write(' '.join(sys.argv[2:]) + '\n')
