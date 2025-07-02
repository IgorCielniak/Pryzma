import json
import sys
import os
import ppm

class pryzmalib():
    def __init__(self):
        interpreter_path = self.get_interpreter_path()
        sys.path.append(interpreter_path)

        import Pryzma

        global interpreter
        interpreter = Pryzma.PryzmaInterpreter()

    def get_interpreter_path(self):
        with open(os.path.expanduser("~/.pryzma/config.json"), 'r') as file:
            data = json.load(file)
        
        return os.path.expanduser(data.get('interpreter_path'))

    def run_file(self, path):
        interpreter.interpret_file(path)

    def run(self, code):
        interpreter.interpret(code)

    def pryzma_import(self, function_name, file_path):
        # This is the function that will be called when the imported module is called
        def internal_function(*args, **kwargs):
            interpreter.interpret("preproc=nan")
            interpreter.import_functions(os.path.abspath(file_path))
            args = list(args)
            for i, arg in enumerate(args):
                if type(arg).__name__ == "str":
                   args[i] = '"' + arg + '"' 
            all_args = ", ".join(args)
            
            return interpreter.evaluate_expression(f'@{function_name}({all_args})')

        class PryzmaModule:
            def __call__(self, *args, **kwargs):
                return internal_function(*args, **kwargs)

        return PryzmaModule()

    def preproc(self, code):
        
        interpreter.preprocess_only = True
        preprocessed_code = interpreter.interpret(code)

        return preproced_code

    def get_interpreter(self):
        return interpreter


    def debug(self, file_path, args):
        interpreter.debug_interpreter(file_path, True, args)

    def ppm_install(self, package_name):
        return ppm.install(package_name)

    def ppm_list(self):
        return ppm.list_packages()

    def ppm_remove(self, package_name):
        return ppm.remove(package_name)

    def ppm_info(self, package_name):
        return ppm.info(package_name)

    def ppm_update(self, package_name):
        return ppm.update(package_name)

    def ppm_update_all(self):
        return ppm.update_all()

def init():
    return pryzmalib()







