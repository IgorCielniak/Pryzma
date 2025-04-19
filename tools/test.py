#!/usr/bin/python

import os
import subprocess

COLORS = {
    "red": "\033[91m",
    "green": "\033[92m",
    "yellow": "\033[93m",
    "blue": "\033[94m",
    "reset": "\033[0m"
}

def print_colored(text, color):
    print(COLORS.get(color, "") + text + COLORS["reset"], end="")

def run_tests():
    test_dir = "tests"
    
    if not os.path.isdir(test_dir):
        print("No 'tests' directory found.")
        return

    for file in os.listdir(test_dir):
        if file.endswith(".test"):
            test_path = os.path.join(test_dir, file)
            expected_path = test_path.replace(".test", ".expected")

            if not os.path.isfile(expected_path):
                print(f"Missing expected output file for {file}")
                continue

            with open(test_path, "r") as test_file:
                command = test_file.read().strip()

            with open(expected_path, "r") as expected_file:
                expected_output = expected_file.read().strip()

            try:
                result = subprocess.run(command, shell=True, text=True, capture_output=True)
                actual_output = result.stdout.strip()

                if actual_output == expected_output:
                    print_colored("[OK] ", "green")
                    print(f"{file} passed")
                else:
                    print_colored("[ERR] ", "red")
                    print(f"{file} failed")
                    print(f"Expected:\n{expected_output}")
                    print(f"Got:\n{actual_output}")

            except Exception as e:
                print_colored(f"Error running {file}: {e}", "red")

if __name__ == "__main__":
    run_tests()

