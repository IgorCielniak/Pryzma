import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..')) 

import pryzmalib

lib = pryzmalib.init()


lib.run('print "hello"')
