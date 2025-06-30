import main

lib = main.pryzmalib()

test = lib.pryzma_import("test", "./module.pryzma")
result = test("gg")  # This calls internal_function
print(result)

