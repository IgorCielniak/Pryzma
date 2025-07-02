import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..')) 

import pryzmalib

lib = pryzmalib.init()


lib.debug(os.path.join(os.path.dirname(__file__), "import.pryzma"), [])

interpreter = lib.get_interpreter()

print(interpreter.variables)
print(interpreter.functions)
