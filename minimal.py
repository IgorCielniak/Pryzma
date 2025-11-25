import re
import sys
import os
import importlib
import importlib.util
import time
import datetime
import json
import shutil
import zipfile
import platform
import random
import ctypes
from collections import UserDict
import lzma

class Reference:
    def __init__(self, var_name):
        self.var_name = var_name

class FuncReference:
    def __init__(self, func_name):
        self.func_name = func_name

class ExternFunction:
    def __init__(self, func):
        self.func = func

    def invoke(self, args):
        prepared = []
        for arg in args:
            prepared.append(self._prepare_arg(arg))
        return self.func(*prepared)

    def _prepare_arg(self, arg):
        if isinstance(arg, str):
            return arg.encode('utf-8')
        if isinstance(arg, bool):
            return int(arg)
        if isinstance(arg, bytearray):
            return bytes(arg)
        if isinstance(arg, memoryview):
            return arg.tobytes()
        if isinstance(arg, (list, tuple)):
            return self._convert_sequence(list(arg))
        return arg

    def _convert_sequence(self, sequence):
        if not sequence:
            return sequence

        if all(isinstance(item, bool) for item in sequence):
            return [int(item) for item in sequence]

        if all(isinstance(item, int) for item in sequence):
            array_type = ctypes.c_longlong * len(sequence)
            return array_type(*sequence)

        if all(isinstance(item, float) for item in sequence):
            array_type = ctypes.c_double * len(sequence)
            return array_type(*sequence)

        if all(isinstance(item, (bytes, bytearray, str, memoryview)) for item in sequence):
            converted = []
            for item in sequence:
                if isinstance(item, str):
                    converted.append(item.encode('utf-8'))
                elif isinstance(item, bytearray):
                    converted.append(bytes(item))
                elif isinstance(item, memoryview):
                    converted.append(item.tobytes())
                else:
                    converted.append(item)
            array_type = ctypes.c_char_p * len(converted)
            return array_type(*converted)

        return [self._prepare_arg(item) for item in sequence]

class PyExternFunction:
    def __init__(self, func):
        self.func = func

    def invoke(self, args):
        return self.func(*args)

class eval_dict(UserDict):
    def __getitem__(self, key):
        value = super().__getitem__(key)
        return value() if callable(value) else value

class PryzmaInterpreter:
    
    def __init__(self):
        self.variables = eval_dict({})
        self.functions = {}
        self.structs = {}
        self.locals = {}
        self.custom_handlers = {}
        self.deleted_keywords = []
        self.variables["interpreter_path"] = __file__
        self.variables["err"] = 0
        self.in_try_block = False
        self.in_func = [False]
        self.function_tracker = [None]
        self.function_ids = [None]
        self.current_func_name = None
        self.preprocess_only = False
        self.no_preproc = False
        self.forward_declare = False
        self.nan = False
        self.return_stops = False
        self.return_val = None
        self.break_stack = []
        self.main_file = 1
        self.mem = bytearray(4096)
        self.fail = False
        self.unpack_ = False
        self.lines_map = []
        self.lines_map_done = False
        self.defer_stack = {}
        self.escape = False
        self.in_loop = False
        self.debug = False
        self.gc = True

    def interpret_file(self, file_path, *args):
        self.file_path = file_path.strip('"')
        self.variables["argv"] = args
        self.variables["__file__"] = os.path.abspath(file_path)
        try:
            with open(file_path, "rb") as f:
                data = f.read()
            if data.startswith("prz".encode('utf-8')):
                data = data[3:]
                self.unpack_ = True

            if self.unpack_ == True:
                self.pre_interpret(self.unpack(file_path))
            else:
                with open(self.file_path, 'r') as file:
                    program = file.read()
                    self.pre_interpret(program)
        except FileNotFoundError:
            print(f"File '{self.file_path}' not found.")

    def preprocess(self, program):
        program = program.splitlines()
        for line in range(0,len(program)):
            program[line] = program[line].split("//")[0]
            if program[line].startswith("#np") or (program[line].startswith("#preproc") and "np" in program[line]):
                self.no_preproc = True
            if self.lines_map_done == False:
                self.lines_map.append((program[line], line))
        self.lines_map_done = True
        in_str = False
        for i, line in enumerate(program):
            for char in line:
                if char == '"':
                    in_str = not in_str
            if in_str == False:
                program[i] += ";"
        program = "".join(program)

        if not self.no_preproc:
            rep_in_func = 0
            char_ = 0
            prog = list(program)
            in_str = False
            for char in prog:
                if char == "{" and not in_str:
                    rep_in_func += 1
                elif char == "}" and not in_str:
                    rep_in_func -= 1
                elif char == '"':
                    in_str = not in_str
                elif rep_in_func != 0  and char == ";" and not in_str:
                    prog[char_] = "|"
                char_ += 1
            prog2 = ""
            for char in prog:
                prog2+=char
            program = prog2

        lines = re.split(r';(?=(?:[^"]*"[^"]*")*[^"]*$)', program)
        return [stmt.strip() for stmt in lines if stmt.strip()]

    def pre_interpret(self, program):
        lines = self.preprocess(program)

        if self.preprocess_only == True:
            for line in lines:
                print(line)
            try:
                return lines
            except:
                pass
            finally:
                sys.exit()

        if self.forward_declare == True:
            self.forward_declare = False
            for i, line in enumerate(lines):
                self.current_line = i
                if line.startswith("/"):
                    self.interpret(line)
                    lines[i] = ""
            self.current_line = 0

        for i in range(0, len(lines)):
            if lines[i].startswith("#replace"):
                a, b = lines[i][8:].split("->")
                a = str(self.evaluate_expression(a.strip()))
                b = str(self.evaluate_expression(b.strip()))
                for i, line in enumerate(lines):
                    lines[i] = re.sub(a, b, line)
            else:
                self.interpret(lines[i])

    def interpret(self, line):
        lines = re.split(r';(?=(?:[^"]*"[^"]*")*[^"]*$)', line)
        for line in lines:
            if self.main_file < 1:
                self.no_preproc = False

            self.main_file -= 1

            if not self.in_func[-1]:
                self.current_line = 0

            for stmt, num in self.lines_map:
                if line.startswith(stmt.strip()) and stmt.strip() != "":
                    if not self.in_loop:
                        self.lines_map.remove((stmt, num))
                    self.current_line = num + 1
                    break
            line = line.strip()

            if line == "" or line.startswith("//"):
                return
            if "//" in line:
                line = line.split("//")[0]

            deleted_keyword = False

            for key_word in self.deleted_keywords:
                if key_word in line and not (line.startswith("disablekeyword(") or line.startswith("enablekeyword(")):
                    keyword = key_word
                    deleted_keyword = True

            if deleted_keyword:
                self.error(1, f"Error at line {self.current_line}: keyword deleted '{keyword}'")
                return

            handled = False
            for handler in self.custom_handlers.values():
                if handler(self, line):
                    handled = True
                    break

            if handled:
                return

            if self.gc == True:
                to_remove = []
                for var in self.locals:
                    self.locals[var] = [item for item in self.locals[var] if self.ref_to_local_exists(var) or item[2] in self.function_ids]
                    if not self.locals[var]:
                        to_remove.append(var)
                for var in to_remove:
                    self.locals.pop(var)

            try:
                if line.startswith("print"):
                    value = line[5:].strip()
                    self.print_value(value)
                elif line.startswith("input"):
                    variable = line[5:].strip()
                    self.custom_input(variable)
                elif line.startswith("#"):
                    if line.startswith("#preproc"):
                        if "=" in line:
                            self.process_args(line.split("=")[1].split(","))
                    elif line.startswith("#insert"):
                        file_path = self.evaluate_expression(line[7:].strip())
                        program = None
                        with open(file_path, "rb") as f:
                            data = f.read()
                        if data.startswith("prz".encode('utf-8')):
                            program = self.decompress(data[3:])
                        if not program:
                            with open(file_path, 'r') as file:
                                program = file.read()
                        self.pre_interpret(program)
                    elif line == "#shell":
                        while True:
                            code = input("/// ")
                            if code == "exit":
                                break
                            shell(code)
                    else:
                        self.process_args(line[1:].split(","))
                elif line.startswith("{"):
                    variables, instance = line.split("=")
                    variables = variables.strip()
                    instance = instance.strip()
                    args = re.split(r',\s*(?=(?:[^"]*"[^"]*")*[^"]*$)', variables[1:-1])
                    if instance in args:
                        self.error(39, f"Error at line {self.current_line}: overlaping names of struct instance and one of variables used for destructuring")
                        return
                    for i, key in enumerate(self.variables[instance].keys()):
                        self.variables[args[i]] = self.variables[instance][key]
                elif line.startswith("struct"):
                    line = line[6:]
                    name, fields = line[:-1].split("{", 1)
                    name = name.strip()
                    fields = self.struct_split(fields.strip())
                    for i, field in enumerate(fields):
                        fields[i] = field.strip()
                    fields = list(filter(None, fields))
                    fields_dict = {}
                    for field in fields:
                        if not field:
                            continue
                        if "=" not in field:
                            fields_dict[field] = None
                        else:
                            key, value = field.split("=", 1)
                            fields_dict[key.strip()] = self.evaluate_expression(value.strip()) if not repr(value.strip()).startswith("@") else value.strip()
                    self.structs[name] = fields_dict
                elif line.startswith("foreach"):
                    line = line[7:].strip()
                    args, action = line.strip()[1:-1].split("){", 1)
                    char_ = 0
                    rep_in_for = 0
                    for_body = list(action)
                    for char in for_body:
                        if char == "{":
                            rep_in_for += 1
                        elif char == "}":
                            rep_in_for -= 1
                        elif rep_in_for == 0  and char == "|":
                            for_body[char_] = "#@!$^%"
                        char_ += 1

                    for_body2 = ""
                    for char in for_body:
                        for_body2 += char
                    actions = for_body2.split("#@!$^%")
                    loop_var, list_name = args.split(",")
                    loop_var = loop_var.strip()
                    list_name = list_name.strip()
                    for action in actions:
                        action = action.strip()

                    self.break_stack.append(False)

                    if list_name in self.variables:
                        for val in self.variables[list_name]:
                            self.variables[loop_var] = val
                            for action in actions:
                                self.interpret(action)
                                if self.break_stack[-1]:
                                    break
                            if self.break_stack[-1]:
                                break
                    else:
                        self.error(41, f"Error at line {self.current_line}: List not found for the foreach function.")

                    self.break_stack.pop()
                elif line.startswith("for"):
                    line = line[3:].strip()
                    range_expr, action = line.strip()[1:-1].split("){", 1)
                    char_ = 0
                    rep_in_for = 0
                    for_body = list(action)
                    for char in for_body:
                        if char == "{":
                            rep_in_for += 1
                        elif char == "}":
                            rep_in_for -= 1
                        elif rep_in_for == 0  and char == "|":
                            for_body[char_] = "*!@#$%&"
                        char_ += 1

                    for_body2 = ""
                    for char in for_body:
                        for_body2 += char
                    actions = for_body2.split("*!@#$%&")
                    loop_var, range_expr = range_expr.split(",")
                    loop_var = loop_var.strip()
                    range_expr = range_expr.strip()
                    for action in actions:
                        action = action.strip()
                    self.in_loop = True
                    self.for_loop(loop_var, range_expr, actions)
                    self.in_loop = False
                elif line.startswith("if"):
                    else_ = False
                    if "else" in line:
                        line = list(line)
                        else_ = True
                        depth = 0
                        in_str = False
                        for i, char in enumerate(line):
                            if char == "{" and not in_str:
                                depth += 1
                            elif char == "}" and not in_str:
                                depth -= 1
                            elif char == '"':
                                in_str = not in_str
                            elif depth == 0 and char == "e" and line[i + 1] == "l" and line[i + 2] == "s" and line[i + 3] == "e":
                                line[i] = "#"
                                line[i + 1] = "$"
                                line[i + 2] = "%"
                                line[i + 3] = "@"
                        sline = "".join(line).split("#$%@")
                        line = sline[0]
                        else_part = sline[1]
                    line = line[2:]
                    if "elif" in line:
                        line = list(line)
                        depth = 0
                        in_str = False
                        for i, char in enumerate(line):
                            if char == "{" and not in_str:
                                depth += 1
                            elif char == "}" and not in_str:
                                depth -= 1
                            elif char == '"':
                                in_str = not in_str
                            elif depth == 0 and char == "e" and line[i + 1] == "l" and line[i + 2] == "i" and line[i + 3] == "f":
                                line[i] = "#"
                                line[i + 1] = "$"
                                line[i + 2] = "&"
                                line[i + 3] = "@"
                        line = "".join(line)
                    branches = line.split("#$&@")
                    handeled = False
                    for branch in branches:
                        if handeled == True:
                            break
                        condition, action = branch.strip()[1:-1].split("){", 1)
                        handeled = False
                        char_ = 0
                        rep_in_if = 0
                        if_body = list(action)
                        for char in if_body:
                            if char == "{":
                                rep_in_if += 1
                            elif char == "}":
                                rep_in_if -= 1
                            elif rep_in_if == 0  and char == "|":
                                if_body[char_] = "#!%&*"
                            char_ += 1
                        if_body2 = ""
                        for char in if_body:
                            if_body2 += char
                        actions = if_body2.split("#!%&*")
                        if self.evaluate_expression(condition.strip()):
                            handeled = True
                            for action in actions:
                                self.interpret(action)

                    if handeled == False and else_:
                        char_ = 0
                        rep_in_if = 0
                        body = list(else_part[1:-1])
                        for char in body:
                            if char == "{":
                                rep_in_if += 1
                            elif char == "}":
                                rep_in_if -= 1
                            elif rep_in_if == 0  and char == "|":
                                body[char_] = "$@#%^&"
                            char_ += 1
                        body2 = ""
                        for char in body:
                            body2 += char
                        actions = body2.split("$@#%^&")
                        for action in actions:
                            self.interpret(action)
                elif line.startswith("while"):
                    line = line[5:]
                    condition, action = line.strip()[1:-1].split("){", 1)
                    char_ = 0
                    rep_in_if = 0
                    if_body = list(action)
                    for char in if_body:
                        if char == "{":
                            rep_in_if += 1
                        elif char == "}":
                            rep_in_if -= 1
                        elif rep_in_if == 0  and char == "|":
                            if_body[char_] = "%$#@!"
                        char_ += 1
                    if_body2 = ""
                    for char in if_body:
                        if_body2 += char
                    actions = if_body2.split("%$#@!")
                    self.break_stack.append(False)
                    while self.evaluate_expression(condition):
                        for action in actions:
                            self.interpret(action)
                            if self.break_stack[-1]:
                                break
                        if self.break_stack[-1]:
                            break
                    self.break_stack.pop()
                elif line.startswith("/"):
                    function_definition = line[1:].split("{", 1)
                    if len(function_definition) == 2:
                        function_name = function_definition[0].strip()
                        function_body = function_definition[1].strip()[:-1]
                        char_ = 0
                        rep_in_func = 0
                        function_body = list(function_body)
                        in_str = False
                        for char in function_body:
                            if char == "{" and not in_str:
                                rep_in_func += 1
                            elif char == "}" and not in_str:
                                rep_in_func -= 1
                            elif char == '"':
                                in_str = not in_str
                            elif rep_in_func == 0  and char == "|" and not in_str:
                                function_body[char_] = "@#%^$"
                            char_ += 1
                        function_body2 = ""
                        for char in function_body:
                            function_body2 += char
                        function_body = list(filter(None, function_body2.split("@#%^$")))
                        self.functions[function_name] = function_body
                    else:
                        self.error(2, f"Invalid function definition at line {self.current_line}")
                elif line.startswith("@"):
                    self.in_func.append(True)
                    function_name = line[1:].strip()
                    self.variables["args"] = []
                    if "(" in function_name:
                        function_name, arg = function_name.split("(", 1)
                        self.current_func_name = function_name
                        if arg.endswith(")"):
                            arg = arg[:-1]
                        if arg:
                            arg = re.split(r',\s*(?=(?:[^"]*"[^"]*")*[^"]*$)', arg)
                            for args in range(len(arg)):
                                arg[args] = self.evaluate_expression(arg[args].strip())
                            self.variables["args"] = arg
                    self.function_tracker.append(function_name)
                    self.function_ids.append(random.randint(0,100000000))
                    var_entry = self.variables.data.get(function_name)
                    if isinstance(var_entry, FuncReference):
                        function_name = var_entry.func_name
                        var_entry = self.variables.data.get(function_name)

                    if isinstance(var_entry, (ExternFunction, PyExternFunction)):
                        try:
                            result = var_entry.invoke(self.variables["args"])
                            self.ret_val = result
                        except Exception as e:
                            self.error(12, f"Error while calling extern function '{function_name}': {e}")
                        finally:
                            self.in_func.pop()
                            self.function_tracker.pop()
                            self.function_ids.pop()
                        return
                    if function_name not in self.functions:
                        self.error(38, f"Error at line {self.current_line}: Referenced function '{function_name}' no longer exists")
                        return
                    if function_name in self.functions:
                        try:
                            command = 0
                            while command < len(self.functions[function_name]):
                                inst = self.functions[function_name][command]
                                self.interpret(inst)
                                if self.return_stops and inst.strip().startswith("return"):
                                    break
                                command += 1
                        finally:
                            func_id = self.function_ids[-1]
                            if (function_name, func_id) in self.defer_stack:
                                while self.defer_stack[(function_name, func_id)]:
                                    deferred = self.defer_stack[(function_name, func_id)].pop()
                                    deferred = deferred.split("|")
                                    for line in deferred:
                                        self.interpret(line.strip())
                            if self.escape == False:
                                if self.gc == True:
                                    to_remove = []
                                    for var in self.locals:
                                        self.locals[var] = [item for item in self.locals[var] if item[2] != func_id]
                                        if not self.locals[var]:
                                            to_remove.append(var)
                                    for var in to_remove:
                                        self.locals.pop(var)
                    else:
                        self.error(3, f"Error at line {self.current_line}: Function '{function_name}' is not defined.")
                    self.in_func.pop()
                    self.function_tracker.pop()
                    self.function_ids.pop()
                elif line.startswith("pyeval(") and line.endswith(")"):
                    parts = re.split(r',\s*(?=(?:[^"]*"[^"]*")*[^"]*$)', line[7:-1])
                    if len(parts) == 1:
                        eval(self.evaluate_expression(parts[0]))
                    else:
                        eval(self.evaluate_expression(parts[0]), self.evaluate_expression(parts[1]))
                elif line.startswith("pyexec(") and line.endswith(")"):
                    parts = re.split(r',\s*(?=(?:[^"]*"[^"]*")*[^"]*$)', line[7:-1])
                    if len(parts) == 1:
                        exec(self.evaluate_expression(parts[0]))
                    else:
                        exec(self.evaluate_expression(parts[0]),self.evaluate_expression(parts[1]))
                elif line.startswith("exec(") and line.endswith(")"):
                    code = re.split(r',\s*(?=(?:[^"]*"[^"]*")*[^"]*$)', line[5:-1])
                    for part in code:
                        self.interpret(self.evaluate_expression(part))
                elif line.startswith("eval(") and line.endswith(")"):
                    code = re.split(r',\s*(?=(?:[^"]*"[^"]*")*[^"]*$)', line[5:-1])
                    for part in code:
                        self.evaluate_expression(part)
                elif line.startswith("isolate(") and line.endswith(")"):
                    args = re.split(r',\s*(?=(?:[^"]*"[^"]*")*[^"]*$)', line[8:-1])
                    isolated_interpreter = None
                    for arg in args:
                        if arg.startswith("isolate"):
                            args.remove(arg)
                            isolated_interpreter = self.variables[arg.split("=", 1)[1].strip()]
                    if not isolated_interpreter:
                        isolated_interpreter = PryzmaInterpreter()
                    for part in args:
                        isolated_interpreter.interpret(self.evaluate_expression(part))
                elif line.startswith("try{") and line.endswith("}"):
                    self.in_try_block = True
                    catch_block = None
                    if "catch(" in line:
                        line, catch_block = line.split("catch(", 1)
                    rep_in_line = 0
                    char_ = 0
                    in_str = False
                    chars = list(line[4:-1])
                    for char in chars:
                        if char == "{":
                            rep_in_line += 1
                        elif char == "}":
                            rep_in_line -= 1
                        elif not in_str and char == '"':
                            in_str = True
                        elif in_str and char == '"':
                            in_str = False
                        elif (rep_in_line == 0 and char == "|" and not in_str):
                            chars[char_] = "@!#$%^"
                        char_ += 1
                    body = "".join(chars)
                    instructions = body.split("@!#$%^")
                    error = 0
                    for instruction in instructions:
                        self.interpret(instruction.strip())
                        if self.variables["err"] != 0:
                            error = self.variables["err"]
                    self.variables["err"] = error
                    if catch_block:
                        err_code, instructions = catch_block[:-1].split("){", 1)
                        if int(err_code) == error:
                            instructions = instructions.split("|")
                            for instruction in instructions:
                                self.interpret(instruction.strip())
                    self.in_try_block = False
                elif line.startswith("int"):
                    line = line[3:].strip()
                    if "=" in line:
                        variable, expression = line.split("=", 1)
                        variable = variable.strip()
                        expression = expression.strip()
                        self.variables[variable] = int(self.evaluate_expression(expression))
                    else:
                        variable = line.strip()
                        self.variables[line] = 0
                elif line.startswith("str"):
                    line = line[3:].strip()
                    if "=" in line:
                        variable, expression = line.split("=", 1)
                        variable = variable.strip()
                        expression = expression.strip()
                        self.variables[variable] = str(self.evaluate_expression(expression))
                    else:
                        variable = line.strip()
                        self.variables[line] = ""
                elif line.startswith("loc "):
                    var, value = line[3:].split("=", 1)
                    var = var.strip()
                    value = self.evaluate_expression(value.strip())
                    if var not in self.locals:
                        self.locals[var] = []
                    self.locals[var].append((value, self.function_tracker[-1], self.function_ids[-1]))
                elif line.startswith("assert"):
                    parts = line[6:].strip().split(",", 1)
                    condition = parts[0].strip()
                    message = parts[1].strip()

                    result = eval(condition, {}, self.variables)
                    if not result:
                        raise AssertionError(f"AssertionError: {self.evaluate_expression(message)}")
                elif "=" in line and not line.strip().startswith(("if", "while")) and not any(op in line for op in ["+=", "-=", "==", "!=", "<=", ">="]):
                    variables, expression = line.split('=', 1)
                    variables = variables.strip().split(",")
                    expression = expression.strip()
                    for variable in variables:
                        ref = False
                        if variable.lstrip("*") in self.variables:
                            if isinstance(self.variables[variable.lstrip("*")], Reference):
                                var = self.variables[variable.lstrip("*")].var_name
                                if var in self.locals:
                                    variable = var
                                    ref = True
                        if variable.lstrip("*") in self.locals:
                            if isinstance(self.locals[variable.lstrip("*")][0], Reference):
                                variable = self.locals[variable.lstrip("*")][0].var_name
                        if variable.lstrip("*") in self.locals:
                            self.assign_value_local(variable, expression, ref)
                        else:
                            self.assign_value(variable.strip(), expression)
                elif "+=" in line:
                    line = line.split("+=")
                    if len(line) != 2:
                        self.error(4, f"Error at line {self.current_line}: Too much arguments")
                        return
                    var = line[0].strip()
                    var2 = line[1].strip()
                    self.increment_var(var, var2)
                elif "-=" in line:
                    line = line.split("-=")
                    if len(line) != 2:
                        self.error(5, f"Error at line {self.current_line}: Too much arguments")
                        return
                    var = line[0].strip()
                    var2 = line[1].strip()
                    self.decrement_var(var, var2)
                elif line.startswith("use"):
                    if "with" in line:
                        line, directive = line.split("with")
                        if directive.strip() != "":
                            nan = self.nan
                            fd = self.forward_declare
                            np = self.no_preproc
                            self.process_args(directive.strip()[1:].split(","))
                            alias = None
                            if " as " in line:
                                file_path, alias = line[3:].strip().split(" as ")
                            else:
                                file_path = line[3:].strip()
                            self.import_functions(file_path, alias)
                            self.nan = nan
                            self.forward_declare = fd
                            self.no_preproc = np
                    else:
                        file_path = line[3:].strip()
                        alias = None
                        if " as " in line:
                            file_path, alias = file_path.split(" as ")
                        self.import_functions(file_path, alias)
                elif line.startswith("from"):
                    if "with" in line:
                        line, directive = line.split("with")
                        line = line.strip()
                        module, functions = line[4:].strip().split("use")
                        module = module.strip()
                        if '/' in module or '\\' in module:
                            pass
                        else:
                            if "::" in module:
                                args = module.split("::")
                                file = args.pop()
                                folder = "/".join(args)
                                module = f"{PackageManager.user_packages_path}/{folder}/{file}.pryzma"
                            else:
                                module = f"{PackageManager.user_packages_path}/{module}/{module}.pryzma"
                        functions = functions.strip().split(",")
                        if directive.strip() != "":
                            nan = self.nan
                            fd = self.forward_declare
                            np = self.no_preproc
                            self.process_args(directive.strip()[1:].split(","))
                            for function in functions:
                                self.load_function_from_file(module, function.strip())
                            self.nan = nan
                            self.forward_declare = fd
                            self.no_preproc = np
                    else:
                        module, functions = line[4:].strip().split("use")
                        module = module.strip()
                        if '/' in module or '\\' in module:
                            pass
                        else:
                            if "::" in module:
                                args = module.split("::")
                                file = args.pop()
                                folder = "/".join(args)
                                module = f"{PackageManager.user_packages_path}/{folder}/{file}.pryzma"
                            else:
                                module = f"{PackageManager.user_packages_path}/{module}/{module}.pryzma"
                        functions = functions.strip().split(",")
                        for function in functions:
                            self.load_function_from_file(module, function.strip())
                elif line.startswith("copy"):
                    list1, list2 = line[4:].split(",")
                    list1 = list1.strip()
                    list2 = list2.strip()
                    for element in self.variables[list1]:
                        self.variables[list2].append(element)
                elif line.startswith("append"):
                    list_name, value = line[6:].split(",")
                    list_name = list_name.strip()
                    value = value.strip()
                    self.append_to_list(list_name, value)
                elif line.startswith("pop"):
                    list_name, index = line[3:].split(",")
                    list_name = list_name.strip()
                    index = index.strip()
                    self.pop_from_list(list_name, index)
                elif line.startswith("remove") and not line.startswith("remove_path("):
                    list_name, var = line[6:].split(",")
                    list_name = list_name.strip()
                    var = var.strip()
                    self.variables[list_name].remove(self.evaluate_expression(var))
                elif line.startswith("sys(") and line.endswith(")"):
                    os.system(self.evaluate_expression(line[4:-1].strip()))
                elif line.startswith("file_write(") and line.endswith(")"):
                    line = re.split(r',\s*(?=(?:[^"]*"[^"]*")*[^"]*$)', line[11:-1])
                    if len(line) == 3:
                        file_path = self.evaluate_expression(line[0].strip())
                        mode = self.evaluate_expression(line[1].strip())
                        content = self.evaluate_expression(line[2].strip())
                        self.write_to_file(file_path, mode, str(content))
                    else:
                        self.error(6, f"Error at line {self.current_line}: Invalid number of arguments for write()")
                elif line.startswith("delvar(") and line.endswith(")"):
                    self.variables.pop(self.evaluate_expression(line[7:-1]))
                elif line.startswith("delfunc(") and line.endswith(")"):
                    self.functions.pop(self.evaluate_expression(line[8:-1]))
                elif line.startswith("disablekeyword(") and line.endswith(")"):
                    args = re.split(r',\s*(?=(?:[^"]*"[^"]*")*[^"]*$)', line[15:-1])
                    for arg in args:
                        self.deleted_keywords.append(self.evaluate_expression(arg))
                elif line.startswith("enablekeyword(") and line.endswith(")"):
                    args = re.split(r',\s*(?=(?:[^"]*"[^"]*")*[^"]*$)', line[14:-1])
                    for arg in args:
                        self.deleted_keywords.remove(self.evaluate_expression(arg))
                elif "++" in line:
                    variable = line.replace("++", "").strip()
                    self.increment_var(variable, "1")
                elif "--" in line:
                    variable = line.replace("--", "").strip()
                    self.decrement_var(variable, "1")
                elif line.startswith("move(") and line.endswith(")"):
                    instructions = line[5:-1].split(",")
                    if len(instructions) != 3:
                        self.error(7, f"Error at line {self.current_line}: Invalid move instruction syntax. Expected format: move(old index, new index, list name)")
                        return
                    list_name = instructions[2].strip()
                    try:
                        old_index = int(instructions[0])
                        new_index = int(instructions[1])
                        value = self.variables[list_name].pop(old_index)
                        self.variables[list_name].insert(new_index, value)
                    except ValueError:
                        self.error(8, f"Error at line {self.current_line}: Invalid index")
                elif line.startswith("swap(") and line.endswith(")"):
                    instructions = line[5:-1].split(",")
                    if len(instructions) != 3:
                        self.error(9, f"Error at line {self.current_line}: Invalid swap instruction syntax. Expected format: swap(index 1, index 2, list name)")
                        return
                    list_name = instructions[2].strip()
                    try:
                        index_1 = int(self.evaluate_expression(instructions[0].strip()))
                        index_2 = int(self.evaluate_expression(instructions[1].strip()))
                        self.variables[list_name][index_1], self.variables[list_name][index_2] = self.variables[list_name][index_2], self.variables[list_name][index_1]
                    except ValueError:
                        self.error(10, "Invalid index for swap()")
                elif line.startswith("call"):
                    call_statement = line[4:].strip()
                    file_name, function_name, args = self.parse_call_statement(call_statement)
                    self.call_function_from_file(file_name, function_name, args)
                elif line.startswith("ccall"):
                    call_statement = line[5:].strip()
                    file_name, function_name, args = self.parse_call_statement(call_statement)
                    self.ccall_function_from_file(file_name, function_name, args)
                elif line.startswith("load(") and line.endswith(")"):
                    self.load_module(self.evaluate_expression(line[5:-1]))
                elif line.startswith("wait(") and line.endswith(")"):
                    time_to_wait = float(self.evaluate_expression(line[5:-1]))
                    time.sleep(time_to_wait)
                elif line.startswith("push(") and line.endswith(")"):
                    dict_name, key, value = re.split(r',\s*(?=(?:[^"]*"[^"]*")*[^"]*$)', line[5:-1])
                    key = self.evaluate_expression(key)
                    value = self.evaluate_expression(value)
                    self.variables[dict_name][key] = value
                elif line.startswith("dpop(") and line.endswith(")"):
                    dict_name, key = re.split(r',\s*(?=(?:[^"]*"[^"]*")*[^"]*$)', line[5:-1])
                    key = self.evaluate_expression(key)
                    self.variables[dict_name].pop(key)
                elif line.startswith("defer{") and line.endswith("}"):
                    if (self.function_tracker[-1], self.function_ids[-1]) in self.defer_stack:
                        self.defer_stack[(self.function_tracker[-1], self.function_ids[-1])].append(line[6:-1])
                    else:
                        self.defer_stack[(self.function_tracker[-1], self.function_ids[-1])] = []
                        self.defer_stack[(self.function_tracker[-1], self.function_ids[-1])].append(line[6:-1])
                elif line.startswith("return"):
                    self.ret_val = self.evaluate_expression(line[6:].strip())
                elif line == "break":
                    self.break_stack[-1] = True
                elif (line.startswith("asm{") or line.startswith("asm {")) and line.endswith("}"):
                    try:
                        from keystone import Ks, KS_ARCH_X86, KS_MODE_64
                        import ctypes, mmap
                    except ImportError:
                        print("ERROR: missing keystone")
                        return

                    line = line[4:-1] if line.startswith("asm{") else line[5:-1]
                    code = list(filter(None, line.split("|")))
                    for i in range(len(code)):
                        code[i] = self.evaluate_expression(code[i].strip())

                    if not code:
                        print("No asm instructions found.")
                        return

                    var_mem = {}
                    for name, value in self.variables.items():
                        if isinstance(value, int):
                            var_mem[name] = ctypes.c_int64(value)

                    token_re = re.compile(r"\[|\]|,|0x[0-9A-Fa-f]+|[A-Za-z_][A-Za-z0-9_]*|[-+]?\d+|\S")

                    def tokenize(line):
                        return token_re.findall(line)

                    ARITH_OPS = {"add", "sub", "imul", "and", "or", "xor"}

                    def resolve_vars(lines, var_mem):
                        out = []
                        for ln in lines:
                            stripped = ln.strip()
                            if not stripped:
                                continue

                            toks = tokenize(stripped)

                            mnemonic = toks[0].lower() if len(toks) > 0 else ""
                            operands = [t for t in toks[1:] if t != ","]

                            def addr_load(addr_hex, dst_reg):
                                return [f"mov r11, {addr_hex}", f"mov {dst_reg}, qword ptr [r11]"]

                            def addr_store(addr_hex, src_reg):
                                return [f"mov r11, {addr_hex}", f"mov qword ptr [r11], {src_reg}"]

                            if mnemonic == "mov" and len(operands) >= 2:
                                op1, op2 = operands[0], operands[1]

                                if op2 in var_mem and re.match(r"^[er]?[abcd]x$|^r[0-9a-z]+$", op1):
                                    addr = hex(ctypes.addressof(var_mem[op2]))
                                    out.extend(addr_load(addr, op1))
                                    continue

                                if op1 in var_mem:
                                    addr = hex(ctypes.addressof(var_mem[op1]))
                                    out.extend(addr_store(addr, op2))
                                    continue

                                out.append(stripped)
                                continue

                            if mnemonic in ARITH_OPS and len(operands) >= 2:
                                dst, src = operands[0], operands[1]
                                if src in var_mem:
                                    addr = hex(ctypes.addressof(var_mem[src]))
                                    out.append(f"mov r11, {addr}")
                                    out.append(f"{mnemonic} {dst}, qword ptr [r11]")
                                    continue
                                out.append(stripped)
                                continue

                            out.append(stripped)

                        return out

                    resolved_body = resolve_vars(code, var_mem)

                    asm_lines = []
                    asm_lines.append("push r11")
                    asm_lines.extend(resolved_body)
                    asm_lines.append("pop r11")
                    asm_lines.append("ret")

                    asm_text = "\n".join(asm_lines)

                    ks = Ks(KS_ARCH_X86, KS_MODE_64)
                    try:
                        machine_code, count = ks.asm(asm_text)
                    except Exception as e:
                        print("ASM ERROR:", e)
                        return

                    shellcode = bytes(machine_code)

                    size = len(shellcode)
                    if size == 0:
                        print("No bytes assembled.")
                        return

                    exec_mem = mmap.mmap(-1, size, prot=mmap.PROT_READ | mmap.PROT_WRITE | mmap.PROT_EXEC)
                    exec_mem.write(shellcode)
                    exec_mem.seek(0)

                    addr = ctypes.addressof(ctypes.c_char.from_buffer(exec_mem))
                    FUNC = ctypes.CFUNCTYPE(None)
                    func = FUNC(addr)

                    try:
                        func()
                    except Exception as e:
                        print("Runtime error while executing asm:", e)

                    for name, ref in var_mem.items():
                        try:
                            self.variables[name] = ref.value
                        except Exception:
                            pass
                    return
                elif (line.startswith("py{") or line.startswith("py {")) and line.endswith("}"):
                    line = line[3:-1] if line.starstwith("py{") else line[4:-1]
                    code = line.split("|")
                    code = list(filter(None, code))
                    for line in range(len(code)):
                        code[line] = self.evaluate_expression(code[line].strip())
                    exec(";".join(code), {}, self.variables)
                elif line.startswith("mkdir(") and line.endswith(")"):
                    path = self.evaluate_expression(line[6:-1])
                    os.mkdir(path)
                elif line.startswith("makedirs(") and line.endswith(")"):
                    path = self.evaluate_expression(line[9:-1])
                    os.makedirs(path, exist_ok=True)
                elif line.startswith("rmdir(") and line.endswith(")"):
                    path = self.evaluate_expression(line[6:-1])
                    os.rmdir(path)
                elif line.startswith("removedirs(") and line.endswith(")"):
                    path = self.evaluate_expression(line[11:-1])
                    os.removedirs(path)
                elif line.startswith("copy(") and line.endswith(")"):
                    args = self.evaluate_expression(line[5:-1]).split(',')
                    src = args[0].strip()
                    dst = args[1].strip()
                    shutil.copy(src, dst)
                elif line.startswith("copyfile(") and line.endswith(")"):
                    args = self.evaluate_expression(line[9:-1]).split(',')
                    src = args[0].strip()
                    dst = args[1].strip()
                    shutil.copyfile(src, dst)
                elif line.startswith("move(") and line.endswith(")"):
                    args = self.evaluate_expression(line[5:-1]).split(',')
                    src = args[0].strip()
                    dst = args[1].strip()
                    shutil.move(src, dst)
                elif line.startswith("rename(") and line.endswith(")"):
                    args = self.evaluate_expression(line[7:-1]).split(',')
                    src = args[0].strip()
                    dst = args[1].strip()
                    os.rename(src, dst)
                elif line.startswith("remove_path(") and line.endswith(")"):
                    path = self.evaluate_expression(line[12:-1])
                    os.remove(path)
                elif line.startswith("symlink(") and line.endswith(")"):
                    args = self.evaluate_expression(line[8:-1]).split(',')
                    src = args[0].strip()
                    dst = args[1].strip()
                    os.symlink(src, dst)
                elif line.startswith("unlink(") and line.endswith(")"):
                    path = self.evaluate_expression(line[7:-1])
                    os.unlink(path)
                elif line.startswith("match(") and "{" in line:
                    line = line[6:-1]
                    var, cases = line.split("){", 1)
                    var = self.evaluate_expression(var.strip())

                    processed_cases = ""
                    depth = 0

                    for char in list(cases):
                        if char == "{":
                            processed_cases += char
                            depth += 1
                        elif char == "}":
                            processed_cases += char
                            depth -= 1
                        elif depth == 1 and char == "|":
                            processed_cases += "&@$%"
                        else:
                            processed_cases += char

                    cases = processed_cases.split("|")
                    cases = list(filter(None, cases))

                    default_case = None
                    handeled = False

                    for case in cases:
                        case = case.strip()
                        case = case[5:-1].split("){")
                        value = self.evaluate_expression(case[0]) if case[0] != "_" else "_"
                        if value == "_":
                            default_case = case
                            continue
                        if var == value:
                            handeled = True
                            for instruction in case[1].split("&@$%"):
                                self.interpret(instruction)

                    if handeled == False and default_case:
                        for instruction in default_case[1].split("&@$%"):
                            self.interpret(instruction)
                elif line.startswith("write(") and line.endswith(")"):
                    addr, data = line[6:-1].split(",", 1)
                    addr = self.evaluate_expression(addr.strip())
                    data = self.evaluate_expression(data.strip())
                    self.mem[addr] = data
                elif line.startswith("patch(") and line.endswith(")"):
                    f1, f2 = re.split(r',\s*(?=(?:[^"]*"[^"]*")*[^"]*$)', line[6:-1])
                    f1 = self.evaluate_expression(f1)
                    f2 = self.evaluate_expression(f2)
                    if f1 not in self.functions or f2 not in self.functions:
                        self.error(40, "Name of a non existing function pased as an argument to patch()")
                    self.functions[f1] = self.functions[f2]
                elif line.startswith("json_dump(") and line.endswith(")"):
                    args = re.split(r',\s*(?=(?:[^"]*"[^"]*")*[^"]*$)', line[10:-1])
                    obj = self.evaluate_expression(args[0])
                    if len(args) > 1:
                        file_path = self.evaluate_expression(args[1])
                        with open(file_path, "w") as f:
                            json.dump(obj, f)
                    else:
                        print(json.dumps(obj))
                elif line.startswith("using"):
                    parts = line.split()
                    is_global = len(parts) > 2 and parts[1] == "global"
                    instance_name = parts[-1]

                    instance = self.evaluate_expression(instance_name)

                    if isinstance(instance, Reference):
                        instance = self.variables[instance.var_name]

                    if instance is None:
                        self.error(28, f"Error at line {self.current_line}: Unknown variable or expression: {instance_name}")
                        return

                    if not isinstance(instance, dict):
                        self.error(42, f"Error at line {self.current_line}: 'using' statement can only be used with structs.")
                        return

                    if is_global:
                        for key, value in instance.items():
                            self.variables[key] = value
                    elif self.in_func[-1]:
                        for key, value in instance.items():
                            if key not in self.locals:
                                self.locals[key] = []
                            self.locals[key].append((value, self.function_tracker[-1], self.function_ids[-1]))
                    else:
                        for key, value in instance.items():
                            self.variables[key] = value
                elif ".@" in line:
                    var_name, func = line.split(".@", 1)
                    func_name, args = func[:-1].split("(", 1)
                    code = f"@{func_name}({var_name}, {args})"
                    self.interpret(code)
                elif line.startswith("extern"):
                    file_name, func_name = line[6:].strip().split(" ", 1)
                    file_name = file_name.strip('"')

                    func_name = func_name.strip()

                    functions = [func_name]

                    if func_name.startswith("{") and func_name.endswith("}"):
                        functions = re.split(r'[|,]', func_name[1:-1])
                        functions = list(filter(None, functions))
                        for i, func in enumerate(functions):
                            functions[i] = functions[i].strip(",").strip()

                    c_functions = ctypes.CDLL(file_name)

                    for func in functions:
                        try:
                            c_func = getattr(c_functions, func)
                        except AttributeError:
                            print(f"Function '{func}' not found in '{file_name}'.")
                            return
                        self.variables[func] = ExternFunction(c_func)
                elif line.startswith("pyextern"):
                    parts = line.split(None, 2)
                    if len(parts) < 3:
                        self.error(11, f"Invalid pyextern statement at line {self.current_line}: {line}")
                        return

                    module_ref = self.resolve_pyextern_module_reference(parts[1])
                    module = self.load_pyextern_module(module_ref)

                    if module is None:
                        return

                    function_specs = self.parse_pyextern_functions(parts[2])

                    if not function_specs:
                        self.error(11, f"No functions specified for pyextern at line {self.current_line}.")
                        return

                    for func_name, alias in function_specs:
                        py_callable = self.resolve_pyextern_callable(module, func_name)
                        if py_callable is None:
                            print(f"Function '{func_name}' not found in '{module_ref}'.")
                            continue
                        if not callable(py_callable):
                            print(f"Attribute '{func_name}' is not callable in '{module_ref}'.")
                            continue
                        self.variables[alias] = PyExternFunction(py_callable)
                elif line == "stop":
                    sys.exit()
                else:
                    if not handled:
                        self.error(11, f"Invalid statement at line {self.current_line}: {line}")

            except Exception as e:
                self.error(12, f"Error at line {self.current_line}: {e}")

    def error(self, code, message):
        if not self.in_try_block:
            self.in_func_err()
            self.variables["err"] = code
            print(message)
            if self.fail:
                sys.exit()
        else:
            self.variables["err"] = code

    def in_func_err(self):
        if self.in_func[-1]:
            print(f"Error while calling function '{self.function_tracker[-1]}'")

    def ref_to_local_exists(self, local):
        for var in self.variables:
            if isinstance(self.variables[var], Reference) and self.variables[var].var_name == local:
                return True
        for var in self.locals:
            if isinstance(self.locals[var][0], Reference) and self.locals[var][0].var_name == local:
                return True
        return False

    def compress(self, text: str) -> bytes:
        return lzma.compress(text.encode('utf-8'), preset=9 | lzma.PRESET_EXTREME)

    def decompress(self, data: bytes) -> str:
        try:
            return lzma.decompress(data).decode('utf-8')
        except Exception:
            print("Can't decompress data")
            sys.exit()

    def pack(self, file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            prog = f.read()
        prog = ";".join(self.preprocess(prog))
        prog = "#np;" + prog
        return bytes("prz".encode('utf-8')) + self.compress(prog)

    def unpack(self, file_path):
        with open(file_path, "rb") as f:
            data = f.read()
        if data.startswith("prz".encode('utf-8')):
            data = data[3:]
        return self.decompress(data)

    def process_args(self, args):
        for arg in range(0,len(args)):
            args[arg] = args[arg].strip()
        if "fd" in args:
            self.forward_declare = True
        if "np" in args:
            self.no_preproc = True
        if "nan" in args:
            self.nan = True
        if "an" in args:
            self.nan = False
        if "fail" in args:
            self.fail = True
        if "df" in args:
            self.fail = False
        if "rs" in args:
            self.return_stops = True
        if "rds" in args:
            self.return_stops = False
        if "esc" in args:
            self.escape = True
        if "desc" in args:
            self.escape = False
        if "gc" in args:
            self.gc = True
        if "ngc" in args:
            self.gc = False


    def struct_split(self, s):
        result = []
        current = []
        in_quotes = False
        brace_depth = 0
        i = 0
        while i < len(s):
            c = s[i]

            if c == '"':
                in_quotes = not in_quotes
                current.append(c)
            elif (c == '{' or c == '[') and not in_quotes:
                brace_depth += 1
                current.append(c)
            elif (c == '}' or c == ']') and not in_quotes:
                brace_depth -= 1
                current.append(c)
            elif (c == ',' or c == '|') and not in_quotes and brace_depth == 0:
                result.append(''.join(current).strip())
                current = []
            else:
                current.append(c)

            i += 1

        if current:
            result.append(''.join(current).strip())
        return result


    def load_module(self, module_path):
        try:
            module_name = os.path.basename(module_path).replace(".py", "")
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            if hasattr(module, "start"):
                self.custom_handlers[module_name] = module.start
            else:
                self.error(13, f"Module '{module_name}' does not have a 'start' function.")
        except Exception as e:
            self.error(14, f"Error loading module '{module_path}': {e}")

    def write_to_file(self, file_path, mode, content):
        try:
            with open(file_path, mode) as file:
                if isinstance(content, list):
                    for line in content:
                        file.write(f"{line}\n")
                else:
                    file.write(content)
        except Exception as e:
            self.error(15, f"Error at line {self.current_line} while writing to file '{file_path}': {e}")

    def add_or_index(self, expr):
        in_quotes = False
        escape = False
        bracket_depth = 0

        for char in expr:
            if char == '"' and not escape:
                in_quotes = not in_quotes
            elif char == '\\':
                escape = not escape
                continue
            elif not in_quotes:
                if char == '[':
                    bracket_depth += 1
                elif char == ']' and bracket_depth > 0:
                    bracket_depth -= 1
                elif char == '+' and bracket_depth > 0:
                    return True

            escape = False

        return False

    def add_or_str(self, expr):
        in_quotes = False
        escape = False
        has_unquoted_plus = False

        for char in expr:
            if char == '"' and not escape:
                in_quotes = not in_quotes
            elif char == '\\':
                escape = not escape
            elif char == '+' and not in_quotes:
                has_unquoted_plus = True
            else:
                escape = False

        return has_unquoted_plus

    def evaluate_expression(self, expression):
        if re.match(r"^\d+$", expression):
            return int(expression)
        elif expression.startswith("read(") and expression.endswith(")"):
            addr = self.evaluate_expression(expression[5:-1])
            return self.mem[addr]
        elif expression.startswith("/"):
            name = "_lambda" + str(random.getrandbits(32))
            self.interpret("/" + name +  expression[1:])
            return FuncReference(name)
        elif expression.startswith("pyeval(") and expression.endswith(")"):
            parts = re.split(r',\s*(?=(?:[^"]*"[^"]*")*[^"]*$)', expression[7:-1])
            if len(parts) == 1:
                return eval(self.evaluate_expression(parts[0]))
            else:
                return eval(self.evaluate_expression(parts[0]), self.evaluate_expression(parts[1]))
        elif expression.startswith("pyexec(") and expression.endswith(")"):
            parts = re.split(r',\s*(?=(?:[^"]*"[^"]*")*[^"]*$)', expression[7:-1])
            if len(parts) == 1:
                return exec(self.evaluate_expression(parts[0]))
            else:
                return exec(self.evaluate_expression(parts[0]), self.evaluate_expression(parts[1]))
        elif expression.startswith("exec(") and expression.endswith(")"):
            code = re.split(r',\s*(?=(?:[^"]*"[^"]*")*[^"]*$)', expression[5:-1])
            for part in code:
                self.ret_val = None
                self.interpret(self.evaluate_expression(part))
                if self.ret_val != None:
                    return self.ret_val
        elif expression.startswith("eval(") and expression.endswith(")"):
            code = re.split(r',\s*(?=(?:[^"]*"[^"]*")*[^"]*$)', expression[5:-1])
            for part in code:
                result = self.evaluate_expression(part)
                if result != None:
                    return result
        elif expression.startswith("new_isolate(") and expression.endswith(")"):
            return PryzmaInterpreter()
        elif expression.startswith("isolate(") and expression.endswith(")"):
            args = re.split(r',\s*(?=(?:[^"]*"[^"]*")*[^"]*$)', expression[8:-1])
            isolated_interpreter = None
            for arg in args:
                if arg.startswith("isolate"):
                    args.remove(arg)
                    isolated_interpreter = self.variables[arg.split("=", 1)[1].strip()]
            if not isolated_interpreter:
                isolated_interpreter = PryzmaInterpreter()
            for part in args:
                isolated_interpreter.ret_val = None
                isolated_interpreter.interpret(self.evaluate_expression(part))
                if isolated_interpreter.ret_val != None:
                    return isolated_interpreter.ret_val
        elif expression.startswith("replace(") and expression.endswith(")"):
            expression = expression[8:-1]
            parts = re.split(r',\s*(?=(?:[^"]*"[^"]*")*[^"]*$)', expression)
            if len(parts) != 3:
                self.error(16, f"Error at line {self.current_line}: Invalid number of arguments for replace function.")
                return None
            value = self.evaluate_expression(parts[0].strip())
            old = self.evaluate_expression(parts[1].strip())
            new = self.evaluate_expression(parts[2].strip())
            if old == "\\n":
                old = "\n"
            if new == "\\n":
               new = "\n"
            return value.replace(old, new)
        elif expression.startswith("json_dump(") and expression.endswith(")"):
            args = re.split(r',\s*(?=(?:[^"]*"[^"]*")*[^"]*$)', expression[10:-1])
            obj = self.evaluate_expression(args[0])
            if len(args) > 1:
                file_path = self.evaluate_expression(args[1])
                with open(file_path, "w") as f:
                    json.dump(obj, f)
            else:
                return json.dumps(obj)
        elif expression.startswith("json_load(") and expression.endswith(")"):
            arg = self.evaluate_expression(expression[10:-1])
            if os.path.exists(arg):
                with open(arg, "r") as f:
                    return json.load(f)
            else:
                return json.loads(arg)
        elif any(expression.startswith(name) for name in self.structs.keys()) and "{" in expression and "}" in expression:
            name, args = expression[:-1].split("{", 1)
            rep_in_args = 0
            char_ = 0
            in_str = False
            args = list(args)
            for char in args:
                if char == "{" or char == "[":
                    rep_in_args += 1
                elif char == "}" or char == "]":
                    rep_in_args -= 1
                elif not in_str and char == '"':
                    in_str = True
                elif in_str and char == '"':
                    in_str = False
                elif (rep_in_args == 0 and char == "|" and not in_str) or (rep_in_args == 0 and char == "," and not in_str):
                    args[char_] = "$#@"
                char_ += 1
            args_body = ""
            for char in args:
                args_body+=char
            args = args_body

            args = list(filter(None, re.split(r'\$\#\@\s*(?=(?:[^"]*"[^"]*")*[^"]*$)', args)))
            name = name.strip()

            struct_def = self.structs[name]
            result = {}

            pairs = []

            for i, arg in enumerate(args):
                if "=" in arg:
                    args[i] = [arg.strip() for arg in arg.strip().split("=", 1)]
                    pairs.append(i)
                else:
                    args[i] = self.evaluate_expression(arg.strip()) if arg != "" else None

            for i, arg in enumerate(args):
                if i in pairs:
                    key = args[i][0].strip()
                    value = args[i][1].strip()
                    result[key] = self.evaluate_expression(value)

            for i, (key, default_value) in enumerate(struct_def.items()):
                if i < len(args) and args[i] is not None:
                    if key not in result.keys():
                        result[key] = self.evaluate_expression(args[i]) if repr(args[i]).startswith("@") else args[i]
                else:
                    if key not in result.keys():
                        result[key] = self.evaluate_expression(default_value) if repr(default_value).startswith("@") else default_value

            #function stolen from https://stackoverflow.com/questions/2444680/how-do-i-add-my-own-custom-attributes-to-existing-built-in-python-types-like-a
            def attr(e,n,v): #will work for any object you feed it, but only that object
                class tmp(type(e)):
                    def attr(self,n,v):
                        setattr(self,n,v)
                        return self
                return tmp(e).attr(n,v)

            result = attr(result, "__type__", name)

            return result
        elif "+" in expression and self.add_or_str(expression) and not self.add_or_index(expression):
            parts = expression.split("+")
            evaluated_parts = [self.evaluate_expression(part.strip()) for part in parts]
            if all(isinstance(part, str) for part in evaluated_parts):
                return "".join(evaluated_parts)
            elif all(isinstance(part, (int)) for part in evaluated_parts):
                return sum(int(part) for part in evaluated_parts)
            elif all(isinstance(part, (float)) for part in evaluated_parts):
                return sum(float(part) for part in evaluated_parts)
            elif any(isinstance(part, str) for part in evaluated_parts) and any(isinstance(part, (int, float)) for part in evaluated_parts):
                for parts in evaluated_parts:
                    if type(parts) == int:
                        evaluated_parts = [str(item) for item in evaluated_parts]
                return "".join(evaluated_parts)
            elif all(isinstance(part, list) for part in evaluated_parts):
                return sum(evaluated_parts, [])
            elif all(isinstance(part, tuple) for part in evaluated_parts):
                return sum(evaluated_parts ,())
        elif re.match(r'^".*"$', expression):
            return expression[1:-1]
        elif expression.startswith("resplit(") and expression.endswith(")"):
            args = expression[8:-1].strip()
            parts = re.split(r',\s*(?=(?:[^"]*"[^"]*")*[^"]*$)', args)
            if len(parts) != 2:
                self.error(17, f"Error at line {self.current_line}: Invalid number of arguments for resplit(). Expected 2 arguments.")
                return None
    
            regex_pattern = self.evaluate_expression(parts[0].strip())
            string_to_split = self.evaluate_expression(parts[1].strip())
    
            if not isinstance(regex_pattern, str):
                self.error(18, f"Error at line {self.current_line}: The first argument of resplit() must be a string (regex pattern).")
                return None
            regex_pattern = r"{}".format(regex_pattern) 
            if not isinstance(string_to_split, str):
                self.error(19, f"Error at line {self.current_line}: The second argument of resplit() must be a string.")
                return None
    
            try:
                return re.split(regex_pattern, string_to_split)
            except re.error as e:
                self.error(20, f"Error at line {self.current_line}: Invalid regex pattern: {e}")
                return None
        elif expression.startswith("in(") and expression.endswith(")"):
            value1, value2 = re.split(r',\s*(?=(?:[^"]*"[^"]*")*[^"]*$)', expression[3:-1])
            value1 = self.evaluate_expression(value1.strip())
            value2 = self.evaluate_expression(value2.strip())
            try:
                return value2 in value1
            except Exception as e:
                self.error(21, f"in() function error at line {self.current_line}: {e}")
        elif expression.startswith("splitby(") and expression.endswith(")"):
            args = re.split(r',\s*(?=(?:[^"]*"[^"]*")*[^"]*$)', expression[8:-1])
            if len(args) < 2:
                self.error(22, f"Error at line {self.current_line}: Invalid number of arguments for splitby function.")
                return None
            char_to_split = self.evaluate_expression(args[0].strip())
            string_to_split = self.evaluate_expression(args[1].strip())
            if len(args) == 3:
                return string_to_split.split(char_to_split, self.evaluate_expression(args[2].strip()))
            else:
                return string_to_split.split(char_to_split)
        elif expression.startswith("type(") and expression.endswith(")"):
            arg = self.evaluate_expression(expression[5:-1])
            try:
                type_ = arg.__type__
                return str(type_)
            except Exception:
                return str(type(arg).__name__)
        elif expression.startswith("len(") and expression.endswith(")"):
            return len(self.evaluate_expression(expression[4:-1].strip()))
        elif expression.startswith("splitlines(") and expression.endswith(")"):
            return self.variables[expression[11:-1]].splitlines()
        elif expression.startswith("file_read(") and expression.endswith(")"):
            file_path = self.evaluate_expression(expression[10:-1])
            try:
                with open(file_path, 'r') as file:
                    return file.read()
            except FileNotFoundError:
                self.error(23, f"Error at line {self.current_line}: File '{file_path}' not found.")
                return ""
        elif expression.startswith("index(") and expression.endswith(")"):
            args = re.split(r',\s*(?=(?:[^"]*"[^"]*")*[^"]*$)', expression[6:-1])
            if len(args) != 2:
                self.error(24, f"Error at line {self.current_line}: Invalid number of arguments for index function.")
                return None
            list_name = args[0].strip()
            value = args[1].strip()
            if list_name in self.variables and isinstance(self.variables[list_name], list):
                value = self.evaluate_expression(value.strip())
                try:
                    index_value = self.variables[list_name].index(value)
                    return index_value
                except ValueError:
                    self.error(25, f"Error at line {self.current_line}: Value '{value}' not found in list '{list_name}'.")
            else:
                self.error(26, f"Error at line {self.current_line}: Variable '{list_name}' is not a list.")
        elif expression.startswith("all(") and expression.endswith(")"):
            list_name = expression[4:-1]
            if list_name in self.variables and isinstance(self.variables[list_name], list):
                return "".join(map(str, self.variables[list_name]))
            else:
                self.error(27, f"Error at line {self.current_line}: List '{list_name}' is not defined.")
                return None
        elif expression.startswith("isanumber(") and expression.endswith(")"):
            expression = expression[10:-1]
            return str(self.evaluate_expression(expression)).isnumeric()
        elif expression.startswith("dirname(") and expression.endswith(")"):
            return os.path.dirname(self.evaluate_expression(expression[8:-1]))
        elif expression == "timenow":
            return datetime.datetime.now()
        elif expression.startswith("startswith(") and expression.endswith(")"):
            parts = re.split(r',\s*(?=(?:[^"]*"[^"]*")*[^"]*$)', expression[11:-1])
            return self.evaluate_expression(parts[1]).startswith(self.evaluate_expression(parts[0]))
        elif expression.startswith("endswith(") and expression.endswith(")"):
            parts = re.split(r',\s*(?=(?:[^"]*"[^"]*")*[^"]*$)', expression[11:-1])
            return self.evaluate_expression(parts[1]).endsswith(self.evaluate_expression(parts[0]))
        elif expression.startswith("randint(") and expression.endswith(")"):
            range_ = expression[8:-1]
            range_ = range_.split(",")
            return random.randint(self.evaluate_expression(range_[0]), self.evaluate_expression(range_[1]))
        elif expression.startswith("strip(") and expression.endswith(")"):
            return self.evaluate_expression(expression[6:-1]).strip()
        elif expression.startswith("get(") and expression.endswith(")"):
            dict_name, key = re.split(r',\s*(?=(?:[^"]*"[^"]*")*[^"]*$)', expression[4:-1])
            key = self.evaluate_expression(key)
            return self.variables[dict_name][key]
        elif expression.startswith("@"):
            self.ret_val = None
            debuger.debug_interpret_func(expression) if self.debug == True else self.interpret(expression)
            return self.ret_val
        elif expression.startswith("char(") and expression.endswith(")"):
            return chr(self.evaluate_expression(expression[5:-1]))
        elif expression.startswith("join(") and expression.endswith(")"):
            char, value = re.split(r',\s*(?=(?:[^"]*"[^"]*")*[^"]*$)', expression[5:-1])
            char = self.evaluate_expression(char)
            value = self.evaluate_expression(value)
            return char.join(value)
        elif expression.startswith("defined(") and expression.endswith(")"):
            name = expression[8:-1]
            return name in self.variables or name in self.locals or name in self.functions
        elif expression.startswith("is_file(") and expression.endswith(")"):
            path = self.evaluate_expression(expression[8:-1])
            return os.path.isfile(path)
        elif expression.startswith("is_dir(") and expression.endswith(")"):
            path = self.evaluate_expression(expression[7:-1])
            return os.path.isdir(path)
        elif expression.startswith("exists(") and expression.endswith(")"):
            path = self.evaluate_expression(expression[7:-1])
            return os.path.exists(path)
        elif expression.startswith("file_size(") and expression.endswith(")"):
            path = self.evaluate_expression(expression[10:-1])
            return os.path.getsize(path)
        elif expression.startswith("join_path(") and expression.endswith(")"):
            args = self.evaluate_expression(expression[10:-1]).split(',')
            paths = [p.strip() for p in args]
            return os.path.join(*paths)
        elif expression.startswith("abs_path(") and expression.endswith(")"):
            path = self.evaluate_expression(expression[9:-1])
            return os.path.abspath(path)
        elif expression.startswith("basename(") and expression.endswith(")"):
            path = self.evaluate_expression(expression[9:-1])
            return os.path.basename(path)
        elif expression.startswith("split_ext(") and expression.endswith(")"):
            path = self.evaluate_expression(expression[10:-1])
            return os.path.splitext(path)
        elif expression.startswith("list_dir(") and expression.endswith(")"):
            path = self.evaluate_expression(expression[9:-1])
            return os.listdir(path)
        elif expression.startswith("walk(") and expression.endswith(")"):
            path = self.evaluate_expression(expression[5:-1])
            return list(os.walk(path))
        elif expression.startswith("is_link(") and expression.endswith(")"):
            path = self.evaluate_expression(expression[8:-1])
            return os.path.islink(path)
        elif expression.startswith("read_link(") and expression.endswith(")"):
            path = self.evaluate_expression(expression[10:-1])
            return os.readlink(path)
        elif expression.startswith("call"):
            call_statement = expression[4:].strip()
            file_name, function_name, args = self.parse_call_statement(call_statement)
            return self.call_function_from_file(file_name, function_name, args)
        elif expression.startswith("ccall"):
            call_statement = expression[5:].strip()
            file_name, function_name, args = self.parse_call_statement(call_statement)
            return self.ccall_function_from_file(file_name, function_name, args)
        elif "." in expression and not expression.split(".", 1)[0].isdigit():
            name, field = expression.split(".", 1)
            return self.acces_field(name, field)
        elif expression.startswith("&"):
            if expression[1:] in self.variables:
                return Reference(expression[1:])
            elif expression[1:] in self.locals:
                return Reference(expression[1:])
            elif expression[1:] in self.functions:
                return FuncReference(expression[1:])
        elif expression.startswith("*"):
            ref = self.evaluate_expression(expression[1:])
            if isinstance(ref, Reference):
                if ref.var_name in self.variables:
                    return self.variables[ref.var_name]
                elif ref.var_name in self.locals:
                    for i in range(len(self.function_tracker) - 1, -1, -1):
                        for val, func_name, func_id in reversed(self.locals[ref.var_name]):
                            return val
                else:
                    self.error(37, f"Error at line {self.current_line}: Referenced variable '{ref.var_name}' no longer exists")
            else:
                return ref
        elif expression.startswith("fields(") and expression.endswith(")"):
            struct = self.evaluate_expression(expression[7:-1])
            return list(struct.keys())
        elif expression.startswith("is_func(") and expression.endswith(")"):
            value = self.evaluate_expression(expression[8:-1])
            return (
                isinstance(value, FuncReference)
                or isinstance(value, str) and value in self.functions
            )
        elif expression.startswith("ascii(") and expression.endswith(")"):
            return ord(self.evaluate_expression(expression[6:-1]))
        elif expression.startswith("~"):
            value = expression[1:]
            return lambda: self.evaluate_expression(value)
        elif "==" in expression:
            value1 = self.evaluate_expression(expression.split("==")[0].strip())
            value2 = self.evaluate_expression(expression.split("==")[1].strip())
            return value1 == value2
        elif "!=" in expression:
            value1 = self.evaluate_expression(expression.split("!=")[0].strip())
            value2 = self.evaluate_expression(expression.split("!=")[1].strip())
            return value1 != value2
        elif "<=" in expression:
            value1 = self.evaluate_expression(expression.split("<=")[0].strip())
            value2 = self.evaluate_expression(expression.split("<=")[1].strip())
            return value1 <= value2
        elif ">=" in expression:
            value1 = self.evaluate_expression(expression.split(">=")[0].strip())
            value2 = self.evaluate_expression(expression.split(">=")[1].strip())
            return value1 >= value2
        elif "<" in expression:
            value1 = self.evaluate_expression(expression.split("<")[0].strip())
            value2 = self.evaluate_expression(expression.split("<")[1].strip())
            return value1 < value2
        elif ">" in expression:
            value1 = self.evaluate_expression(expression.split(">")[0].strip())
            value2 = self.evaluate_expression(expression.split(">")[1].strip())
            return value1 > value2
        elif expression.startswith("pop"):
            list_name = expression[3:].strip()
            return self.variables[list_name].pop()
        elif expression in self.variables or expression in self.locals:
            if expression in self.locals:
                for i in range(len(self.function_tracker) - 1, -1, -1):
                    for val, func_name, func_id in reversed(self.locals[expression]):
                        if func_name == self.function_tracker[i] and func_id == self.function_ids[i]:
                            return val
            if expression in self.variables:
                return self.variables[expression]
            else:
                self.error(36, f"Error at line {self.current_line}: Variable '{expression}' not found in current scope.")
        else:
            try:
                return eval(expression, {}, self.variables)
            except NameError:
                self.error(28, f"Error at line {self.current_line}: Unknown variable or expression: {expression}")
        return None

    def acces_field(self, name, field):
        obj = self.variables[name.strip()]
        if isinstance(obj, Reference):
            obj = self.variables[obj.var_name]
        parts = re.findall(r'\w+|\[.*?\]', field)

        for part in parts:
            if part.startswith('['):
                index_expr = part[1:-1].strip()
                index = self.evaluate_expression(index_expr)
                obj = obj[index]
            else:
                obj = obj[part.strip()]
        return obj

    def assign_value_local(self, var_name, expression, ref = False):
        value = self.evaluate_expression(expression)
        if isinstance(value, dict):
            value = value.copy()

        if var_name.startswith("*"):
            ref = self.evaluate_expression(var_name[1:].strip())
            if isinstance(ref, Reference):
                var_name = ref.var_name

        if "." in var_name:
            tokens = re.findall(r"[a-zA-Z_]\w*|\[\s*[^\]]+\s*\]", var_name)

            if not tokens:
                raise ValueError("Invalid struct field")

            base_var_name = tokens[0]

            target = None
            for i in range(len(self.function_tracker) - 1, -1, -1):
                for item in reversed(self.locals[base_var_name]):
                    if ref == True:
                        target = item[0]
                        break
                    if item[1] == self.function_tracker[i] and item[2] == self.function_ids[i]:
                        target = item[0]
                        break
                if target is not None:
                    break

            if target is None:
                self.error(36, f"Error at line {self.current_line}: Variable '{base_var_name}' not found in current scope.")
                return

            if isinstance(target, Reference):
                target = self.variables[target.var_name]

            for token in tokens[1:-1]:
                if token.startswith('['):
                    index_expr = token[1:-1].strip()
                    index = self.evaluate_expression(index_expr)
                    target = target[index]
                else:
                    target = target[token]

            last_token = tokens[-1]
            if last_token.startswith('['):
                index_expr = last_token[1:-1].strip()
                index = self.evaluate_expression(index_expr)
                target[index] = value
            else:
                target[last_token] = value
        elif '[' in var_name:
            base_var = var_name.split('[')[0]
            indexes = re.findall(r'\[(.*?)\]', var_name)

            target = None
            for i in range(len(self.function_tracker) - 1, -1, -1):
                for item in reversed(self.locals[base_var]):
                    if ref == True:
                        target = item[0]
                        break
                    if item[1] == self.function_tracker[i] and item[2] == self.function_ids[i]:
                        target = item[0]
                        break
                if target is not None:
                    break

            if target is None:
                self.error(36, f"Error at line {self.current_line}: Variable '{base_var}' not found in current scope.")
                return

            if isinstance(target, Reference):
                target = self.variables[target.var_name]

            for index_expr in indexes[:-1]:
                index = self.evaluate_expression(index_expr)
                target = target[index]

            last_index = self.evaluate_expression(indexes[-1])
            target[last_index] = value
        else:
            for i in range(len(self.function_tracker) - 1, -1, -1):
                for j, item in enumerate(reversed(self.locals[var_name])):
                    if ref == True:
                        self.locals[var_name][len(self.locals[var_name]) - 1 - j] = (value, item[1], item[2])
                        break
                    if item[1] == self.function_tracker[i] and item[2] == self.function_ids[i]:
                        self.locals[var_name][len(self.locals[var_name]) - 1 - j] = (value, item[1], item[2])
                        return

    def assign_value(self, var_name, expression):
        value = self.evaluate_expression(expression)
        if isinstance(value, dict):
            value = value.copy()

        if var_name.startswith("*"):
            ref = self.evaluate_expression(var_name[1:].strip())
            if isinstance(ref, Reference):
                var_name = ref.var_name

        if "." in var_name:
            tokens = re.findall(r"[a-zA-Z_]\w*|\[\s*[^\]]+\s*\]", var_name)

            if not tokens:
                raise ValueError("Invalid struct field")

            var_name = tokens[0]
            if var_name not in self.variables:
                raise KeyError(f"Variable '{var_name}' not found")

            target = self.variables[var_name]
            if isinstance(target, Reference):
                target = self.variables[target.var_name]

            for token in tokens[1:-1]:
                if token.startswith('['):
                    index_expr = token[1:-1].strip()
                    index = self.evaluate_expression(index_expr)
                    target = target[index]
                else:
                    target = target[token]

            last_token = tokens[-1]
            if last_token.startswith('['):
                index_expr = last_token[1:-1].strip()
                index = self.evaluate_expression(index_expr)
                target[index] = value
            else:
                target[last_token] = value
        else:
            if '[' in var_name:
                base_var = var_name.split('[')[0]

                indexes = re.findall(r'\[(.*?)\]', var_name)

                target = self.variables[base_var]
                if isinstance(target, Reference):
                    target = self.variables[target.var_name]

                for index_expr in indexes[:-1]:
                    index = self.evaluate_expression(index_expr)
                    target = target[index]

                last_index = self.evaluate_expression(indexes[-1])
                target[last_index] = value
            else:
                self.variables[var_name] = value

    def increment_var(self, var_name, expression):
        value = self.evaluate_expression(expression)
        if isinstance(value, dict):
            value = value.copy()

        if var_name.startswith("*"):
            ref = self.evaluate_expression(var_name[1:].strip())
            if isinstance(ref, Reference):
                var_name = ref.var_name

        if "." in var_name:
            tokens = re.findall(r"[a-zA-Z_]\w*|\[\s*[^\]]+\s*\]", var_name)

            if not tokens:
                raise ValueError("Invalid struct field")

            var_name = tokens[0]
            if var_name not in self.variables:
                raise KeyError(f"Variable '{var_name}' not found")

            target = self.variables[var_name]
            if isinstance(target, Reference):
                target = self.variables[target.var_name]

            for token in tokens[1:-1]:
                if token.startswith('['):
                    index_expr = token[1:-1].strip()
                    index = self.evaluate_expression(index_expr)
                    target = target[index]
                else:
                    target = target[token]

            last_token = tokens[-1]
            if last_token.startswith('['):
                index_expr = last_token[1:-1].strip()
                index = self.evaluate_expression(index_expr)
                target[index] += value
            else:
                target[last_token] += value
        else:
            if '[' in var_name:
                base_var = var_name.split('[')[0]

                indexes = re.findall(r'\[(.*?)\]', var_name)

                target = self.variables[base_var]
                if isinstance(target, Reference):
                    target = self.variables[target.var_name]

                for index_expr in indexes[:-1]:
                    index = self.evaluate_expression(index_expr)
                    target = target[index]

                last_index = self.evaluate_expression(indexes[-1])
                target[last_index] += value
            else:
                self.variables[var_name] += value

    def decrement_var(self, var_name, expression):
        value = self.evaluate_expression(expression)
        if isinstance(value, dict):
            value = value.copy()

        if var_name.startswith("*"):
            ref = self.evaluate_expression(var_name[1:].strip())
            if isinstance(ref, Reference):
                var_name = ref.var_name

        if "." in var_name:
            tokens = re.findall(r"[a-zA-Z_]\w*|\[\s*[^\]]+\s*\]", var_name)

            if not tokens:
                raise ValueError("Invalid struct field")

            var_name = tokens[0]
            if var_name not in self.variables:
                raise KeyError(f"Variable '{var_name}' not found")

            target = self.variables[var_name]
            if isinstance(target, Reference):
                target = self.variables[target.var_name]

            for token in tokens[1:-1]:
                if token.startswith('['):
                    index_expr = token[1:-1].strip()
                    index = self.evaluate_expression(index_expr)
                    target = target[index]
                else:
                    target = target[token]

            last_token = tokens[-1]
            if last_token.startswith('['):
                index_expr = last_token[1:-1].strip()
                index = self.evaluate_expression(index_expr)
                target[index] -= value
            else:
                target[last_token] -= value
        else:
            if '[' in var_name:
                base_var = var_name.split('[')[0]

                indexes = re.findall(r'\[(.*?)\]', var_name)

                target = self.variables[base_var]
                if isinstance(target, Reference):
                    target = self.variables[target.var_name]

                for index_expr in indexes[:-1]:
                    index = self.evaluate_expression(index_expr)
                    target = target[index]

                last_index = self.evaluate_expression(indexes[-1])
                target[last_index] -= value
            else:
                self.variables[var_name] -= value

    def print_value(self, value):
        char_ = 0
        prog = list(value)
        in_str = False
        depth = 0
        for char in prog:
            if char == '"':
                in_str = not in_str
            elif (char == "{") or (char == "[") or (char == "("):
                depth += 1
            elif (char == "}") or (char == "]") or (char == ")"):
                depth -= 1
            elif char == "," and depth == 0 and not in_str:
                prog[char_] = "&#$%^"
            char_ += 1
        value = "".join(prog)
        parts = value.split("&#$%^")
        part_count = 0
        for part in parts:
            parts[part_count] = self.evaluate_expression(parts[part_count].strip())
            if isinstance(parts[part_count], str):
                parts[part_count] = parts[part_count].replace("\\n", "\n")
            part_count += 1
        for part in parts:
            if not (self.in_try_block and part == None):
                print(part, end="")

    def custom_input(self, variable):
        if "::" in variable:
            variable_name, prompt = variable.split("::", 1)
            variable_name = variable_name.strip()
            prompt = prompt.strip('"')
        else:
            variable_name = variable.strip()
            prompt = ""

        value = self.get_input(prompt)
        self.variables[variable_name] = value


    def for_loop(self, loop_var, range_expr, actions):
        start, end = range_expr.split(":")
        start_val = self.evaluate_expression(start.strip())
        end_val = self.evaluate_expression(end.strip())

        self.break_stack.append(False)

        if isinstance(start_val, int) and isinstance(end_val, int):
            for val in range(start_val, end_val):
                self.variables[loop_var] = val
                for action in actions:
                    self.interpret(action)
                    if self.break_stack[-1]:
                        break
                if self.break_stack[-1]:
                    break
        else:
            self.error(29, f"Error at line {self.current_line}: Invalid range expression for loop.")

        self.break_stack.pop()

    def import_functions(self, file_path, alias=None):
        file_path = file_path.strip('"')
    
        if file_path.startswith("https://") or file_path.startswith("http://"):
            import requests
            name = os.path.basename(file_path).split(".")[0]
            f = requests.get(file_path)
            program = f.text
            lines = self.preprocess(program)

            function_def = False
            function_name = ""
            function_body = []
            for line in lines:
                if line.startswith("/"):
                    if not self.nan:
                        if line[1:].startswith(name+"."):
                            line = "/" + line[1:]
                        else:
                            line = "/" + name + "."  + line[1:]
                    self.interpret(line)
                    if not self.nan:
                        if line.startswith("/"+name+".on_import"):
                            self.interpret("@"+name+".on_import")
                    else:
                        if line.startswith("/on_import"):
                            self.interpret("@on_import")
        elif '/' in file_path or '\\' in file_path:
            self.load_functions_from_file(file_path, alias)
        else:
            if "::" in file_path:
                args = file_path.split("::")
                file = args.pop()
                folder = "/".join(args)
                file_path = f"{PackageManager.user_packages_path}/{folder}/{file}.pryzma"
            else:
                file_path = f"{PackageManager.user_packages_path}/{file_path}/{file_path}.pryzma"
            self.load_functions_from_file(file_path, alias)

    def load_function_from_file(self, file_path, func_name, alias=None):
        if alias:
            name = alias
        else:
            name = os.path.splitext(os.path.basename(file_path))[0]
        try:
            program = None
            with open(file_path, "rb") as f:
                data = f.read()
            if data.startswith("prz".encode('utf-8')):
                program = self.decompress(data[3:])
            if not program:
                with open(file_path, 'r') as file:
                    program = file.read()

            lines = self.preprocess(program)

            function_def = False
            function_name = ""
            function_body = []
            match = False
            for line in lines:
                if line.startswith("/"):
                    if line[1:].startswith(name + "."):
                        if self.nan:
                            line = "/" + line[len(name) + 2:]
                    match = line[1:].startswith(func_name+"{")
                    if match:
                        self.interpret(line)
        except FileNotFoundError:
            self.error(30, f"Error at line {self.current_line}: File '{file_path}' not found.")

    def load_functions_from_file(self, file_path, alias=None):
        if alias:
            name = alias
        else:
            name = os.path.splitext(os.path.basename(file_path))[0]
        try:
            unpack = False
            program = None
            with open(file_path, "rb") as f:
                data = f.read()
            if data.startswith("prz".encode('utf-8')):
                program = self.decompress(data[3:])
            if not program:
                with open(file_path, 'r') as file:
                    program = file.read()

            lines = self.preprocess(program)

            function_def = False
            function_name = ""
            function_body = []
            for line in lines:
                if line.startswith("/"):
                    if not self.nan:
                        if line[1:].startswith(name+"."):
                            line = "/" + line[1:]
                        else:
                            line = "/" + name + "."  + line[1:]
                    self.interpret(line)
                    if not self.nan:
                        if line.startswith("/"+name+".on_import"):
                            self.interpret("@"+name+".on_import")
                    else:
                        if line.startswith("/on_import"):
                            self.interpret("@on_import")
        except FileNotFoundError:
            self.error(30, f"Error at line {self.current_line}: File '{file_path}' not found.")

    def get_input(self, prompt):
        if sys.stdin.isatty():
            return input(prompt)
        else:
            sys.stdout.write(prompt)
            sys.stdout.flush()
            return sys.stdin.readline().rstrip('\n')

    def interpret_file2(self):
        self.file_path = input("Enter the file path of the program: ")
        self.interpret_file(self.file_path)

    def show_license(self):
        license_text = """
Pryzma
Copyright 2025 Igor Cielniak

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
        """

        print(license_text)
    
    def append_to_list(self, list_name, value):
        if "[" in list_name:
            list_name, index = list_name[:-1].split("[")
            self.variables[list_name][self.evaluate_expression(index)].append(self.evaluate_expression(value))
        elif list_name in self.variables:
            self.variables[list_name].append(self.evaluate_expression(value))
        else:
            self.error(31, f"Error at line {self.current_line}: List '{list_name}' does not exist.")

    def pop_from_list(self, list_name, index):
        if list_name in self.variables:
            try:
                index = self.evaluate_expression(index)
                self.variables[list_name].pop(index)
            except IndexError:
                self.error(32, f"Error at line {self.current_line}: Index {index} out of range for list '{list_name}'.")
        else:
            self.error(33, f"Error at line {self.current_line}: List '{list_name}' does not exist.")

    def parse_call_statement(self, statement):
        if statement.startswith("(") and statement.endswith(")"):
            statement = statement[1:-1]
            parts = [part.strip() for part in re.split(r',\s*(?=(?:[^"]*"[^"]*")*[^"]*$)', statement)]

            if len(parts) < 2:
                self.error(34, "Invalid number of arguments for call")

            file_name = self.evaluate_expression(parts[0])
            function_name = self.evaluate_expression(parts[1])

            args = parts[2:]

            for i, arg in enumerate(args):
                args[i] = self.evaluate_expression(arg)

            return file_name, function_name, args
        else:
            self.error(35, "Invalid call statement format. Expected format: call(file_name, function_name, arg1, arg2, ...)")

    def call_function_from_file(self, file_name, function_name, args):
        if not os.path.isfile(file_name):
            print(f"File '{file_name}' does not exist.")
            return

        spec = importlib.util.spec_from_file_location("module.name", file_name)

        if spec is None:
            print(f"Could not load the module from '{file_name}'.")
            return

        module = importlib.util.module_from_spec(spec)

        try:
            spec.loader.exec_module(module)
        except Exception as e:
            print(f"Error loading module '{file_name}': {e}")
            return

        if hasattr(module, function_name):
            func = getattr(module, function_name)
            if callable(func):
                return func(*args)
            else:
                print(f"'{function_name}' is not callable in '{file_name}'.")
        else:
            print(f"Function '{function_name}' is not defined in '{file_name}'.")

    def ccall_function_from_file(self, file_name, function_name, args):
        if not os.path.isfile(file_name):
            print(f"File '{file_name}' does not exist.")
            return

        c_functions = ctypes.CDLL(file_name)

        try:
            c_func = getattr(c_functions, function_name)
        except AttributeError:
            print(f"Function '{function_name}' not found in '{file_name}'.")
            return

        return c_func(*args)

    def resolve_pyextern_module_reference(self, module_expr):
        module_expr = module_expr.strip()

        if module_expr.startswith("\"") and module_expr.endswith("\""):
            return module_expr[1:-1]

        return self.evaluate_expression(module_expr)

    def load_pyextern_module(self, module_ref):
        try:
            if module_ref.endswith(".py") or os.path.sep in module_ref:
                base_file = self.variables.get("__file__", getattr(self, "file_path", os.getcwd()))
                base_dir = os.path.dirname(base_file)

                candidates = []

                if os.path.isabs(module_ref):
                    candidates.append(module_ref)
                else:
                    candidates.append(os.path.abspath(module_ref))
                    candidates.append(os.path.abspath(os.path.join(base_dir, module_ref)))

                module_path = next((path for path in candidates if os.path.isfile(path)), None)
                if module_path is None:
                    print(f"File '{module_ref}' does not exist.")
                    return None

                module_name = f"pryzma_pyextern_{abs(hash(module_path))}"
                spec = importlib.util.spec_from_file_location(module_name, module_path)
                if spec is None or spec.loader is None:
                    print(f"Could not load the module from '{module_path}'.")
                    return None

                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                return module

            return importlib.import_module(module_ref)
        except Exception as e:
            print(f"Error loading python module '{module_ref}': {e}")
            return None

    def parse_pyextern_functions(self, functions_str):
        functions_str = functions_str.strip()
        if not functions_str:
            return []
        if functions_str.startswith("{") and functions_str.endswith("}"):
            raw_entries = re.split(r'[|,]', functions_str[1:-1])
        else:
            raw_entries = [functions_str]

        parsed = []
        for entry in raw_entries:
            entry = entry.strip()
            if not entry:
                continue

            alias = None
            if " as " in entry:
                func_name, alias = entry.split(" as ", 1)
                func_name = func_name.strip()
                alias = alias.strip()
            else:
                func_name = entry

            alias = alias or func_name.split(".")[-1]
            parsed.append((func_name, alias))
        return parsed

    def resolve_pyextern_callable(self, module, func_path):
        target = module
        for attr in func_path.split('.'):
            if not hasattr(target, attr):
                return None
            target = getattr(target, attr)
        return target

    def print_help(self):
        print("""
commands:
    file - run a program from a file
    cls - clear the functions, variables and structs dictionaries
    clear - clear the console
    debug - start debugging mode
    history - show the commands history
    history <number> - execute the command from the history by number
    history clear - clear the commands history
    history <term> - search the commands history for a term
    info - show the interpreter version along with some other information
    ppm - lunch the Pryzma Package Manager shell
    ppm <command> - execute a Pryzma package manager command
    errors - show the error codes table
    exit - exit the interpreter
    reboot - reboot the interpreter
    v - show all variables
    f - show all functions
    s - show all structs
    l - show all locals
    help - show this help
    license - show the license
""")


    def display_system_info():
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        os_info = platform.system() + " " + platform.release()

        cpu_info = platform.processor()

        machine_arch = platform.machine()
        if machine_arch in ['x86_64', 'AMD64']:
            arch_info = '64-bit'
        elif machine_arch in ['i386', 'i686']:
            arch_info = '32-bit'
        else:
            arch_info = 'Unknown'

        print(f"Pryzma {version}")
        print(f"Current Date and Time: {current_time}")
        print(f"Operating System: {os_info} {arch_info} ({machine_arch})")
        print(f"Processor: {cpu_info}")


    def print_error_codes_table():
        print(
"""
1 - Error keyword deleted
2 - Invalid function definition
3 - Function not defined
4 - Too much arguments for +=
5 - Too much arguments for -=
6 - Invalid number of arguments for write()
7 - Invalid move() instruction syntax
8 - Invalid index for move() instruction
9 - Invalid swap() instruction syntax
10 - Invalid index for swap() instruction
11 - Invalid statement
12 - Unknown error
13 - Module does not have a 'start' function.
14 - Error loading module
15 - Error writing to file
16 - Invalid number of arguments for replace function
17 - Invalid number of arguments for resplit function
18 - The first argument of resplit() must be a string (regex pattern).
19 - The second argument of resplit() must be a string.
20 - Invalid regex pattern.
21 - in() function error
22 - Invalid number of arguments for splitby function
23 - File not found
24 - Invalid number of arguments for index function
25 - Value not found in list for index function
26 - Variable is not a list for index function
27 - List not defined for all()
28 - Unknown variable or expression
29 - Invalid range expression for loop
30 - File not found for use function
31 - List does not exist for append function
32 - Index out of range for pop function
33 - List does not exist for pop function
34 - Invalid number of arguments for call.
35 - Invalid call statement format.
36 - Variable not found in current scope.
37 - Referenced variable no longer exists.
38 - Referenced function no longer exists.
39 - Overlaping names of struct instance and one of variables used for destructuring.
40 - Name of a non existing function pased as an argument to patch()
41 - List not found for the foreach function.
42 - 'using' statement can only be used with struct instances.
"""
)

