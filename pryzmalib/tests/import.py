import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..')) 

import pryzmalib

lib = pryzmalib.init()

test = lib.pryzma_import("test", os.path.join(os.path.dirname(__file__), "./module.pryzma"))
result = test("gg")  # This calls internal_function
print(result)

