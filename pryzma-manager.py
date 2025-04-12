import argparse
import os
import sys
import json
import shutil
import subprocess

PRYZMA_PATH = os.path.abspath(os.path.dirname(__file__))
PROJECTS_PATH = os.path.abspath(os.path.join(PRYZMA_PATH, "projects"))
VENVS_PATH = os.path.abspath(os.path.join(PRYZMA_PATH, "venvs"))
CONFIG_PATHS = [
    os.path.abspath("./config.json"),
    os.path.expanduser("~/.pryzma/config.json")
]


def load_config():
    for path in CONFIG_PATHS:
        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)

    print(f"[config] No config file found at {CONFIG_PATHS[0]} or {CONFIG_PATHS[1]}")
    return {}


def init_main_env():
    for path in [VENVS_PATH, PROJECTS_PATH]:
        if not os.path.exists(path):
            os.makedirs(path)
            print(f"[init] Created {path}")


def init_project(name=None, interactive=False):
    if interactive:
        print("[init] Interactive project creation:")
        name = input("Enter project name: ").strip()

    if not name:
        print("[init] Project name is required.")
        return

    path = os.path.join(PROJECTS_PATH, name)
    if os.path.exists(path):
        print(f"[init] Project '{name}' already exists.")
        return

    os.makedirs(path)
    print(f"[init] Created project '{name}' at {path}")


def remove_project(name):
    path = os.path.join(PROJECTS_PATH, name)

    if not os.path.exists(path):
        print(f"[remove] Project '{name}' does not exist.")
        return

    confirm = input(f"[remove] Delete project '{name}'? (y/n): ").lower()
    if confirm == "y":
        try:
            shutil.rmtree(path)
            print(f"[remove] Project '{name}' has been deleted.")
        except Exception as e:
            print(f"[error] Failed to delete project: {e}")
    else:
        print("[remove] Cancelled.")


def list_projects():
    print("[list] Listing all projects...")
    if not os.path.exists(PROJECTS_PATH):
        print("[list] No projects directory found.")
        return

    projects = os.listdir(PROJECTS_PATH)
    if not projects:
        print("[list] No projects found.")
    else:
        for project in projects:
            print(f" - {project}")

def venv_command(action, name=None):
    if action == "create":
        if not name:
            print("[venv] Please provide a name for the virtual environment.")
            return

        target_path = os.path.join(VENVS_PATH, name)
        if os.path.exists(target_path):
            print(f"[venv] Virtual environment '{name}' already exists.")
            return

        config = load_config()
        interpreter_path = config.get("interpreter_path", "Pryzma-programming-language")

        if not os.path.exists(interpreter_path):
            print(f"[venv] Interpreter not found at '{interpreter_path}'")
            return

        os.makedirs(target_path, exist_ok=True)

        if os.path.isdir(interpreter_path):
            os.system(f'cp "{interpreter_path}"/Pryzma.py "{target_path}/"')
        else:
            os.system(f'cp "{interpreter_path}" "{target_path}/"')

        print(f"[venv] Created virtual environment '{name}' in '{target_path}'.")

    elif action == "list":
        if not os.path.exists(VENVS_PATH):
            print("[venv] No virtual environments found.")
            return

        envs = [d for d in os.listdir(VENVS_PATH) if os.path.isdir(os.path.join(VENVS_PATH, d))]
        if not envs:
            print("[venv] No virtual environments available.")
        else:
            print("[venv] Available environments:")
            for env in envs:
                print(f"  - {env}")
    elif action == "remove":
        path = os.path.join(VENVS_PATH, name)

        if not os.path.exists(path):
            print(f"[venv] Venv '{name}' does not exist.")
            return

        confirm = input(f"[venv] Delete venv '{name}'? (y/n): ").lower()
        if confirm == "y":
            try:
                shutil.rmtree(path)
                print(f"[venv] Venv '{name}' has been deleted.")
            except Exception as e:
                print(f"[error] Failed to delete project: {e}")
        else:
            print("[venv] Cancelled.")


def run_script(path=None):
    config = load_config()
    interpreter_path = config.get("interpreter_path", "Pryzma-programming-language")

    if path:
        print(f"[run] Running Pryzma script at '{path}'...")
        sys.path.append(os.path.abspath(interpreter_path))

        try:
            from Pryzma import PryzmaInterpreter
            interpreter = PryzmaInterpreter()
            interpreter.interpret_file(path)
        except ImportError as e:
            print(f"[error] Could not import Pryzma interpreter: {e}")
        except Exception as e:
            print(f"[error] Error running script: {e}")
    else:
        print("[run] Launching Pryzma interpreter...")
        sys.path.append(os.path.abspath(interpreter_path))

        try:
            os.system("python " + os.path.join(interpreter_path, "Pryzma.py"))
        except Exception as e:
            print(f"[error] Error launching interpreter: {e}")


def build_parser():
    parser = argparse.ArgumentParser(prog="pryzma-manager", description="Manage Pryzma projects and environments")
    subparsers = parser.add_subparsers(dest="command")

    # Project group
    proj_parser = subparsers.add_parser("proj", help="Project management commands")
    proj_subparsers = proj_parser.add_subparsers(dest="proj_command")

    proj_init = proj_subparsers.add_parser("init", help="Initialize a new Pryzma project")
    proj_init.add_argument("name", nargs="?", help="Project name")
    proj_init.add_argument("-i", "--interactive", action="store_true", help="Interactive mode")

    proj_remove = proj_subparsers.add_parser("remove", help="Remove a project")
    proj_remove.add_argument("name", help="Project name")

    proj_subparsers.add_parser("list", help="List all Pryzma projects")

    # Run command
    run_parser = subparsers.add_parser("run", help="Run a Pryzma script")
    run_parser.add_argument("path", nargs="?", help="Path to .pryzma script")

    # Venv group
    venv_parser = subparsers.add_parser("venv", help="Manage Pryzma virtual environments")
    venv_subparsers = venv_parser.add_subparsers(dest="venv_command")

    venv_create = venv_subparsers.add_parser("create", help="Create a virtual environment")
    venv_create.add_argument("name", help="Name of the virtual environment")

    venv_create = venv_subparsers.add_parser("remove", help="Remove a virtual environment")
    venv_create.add_argument("name", help="Name of the virtual environment")

    venv_subparsers.add_parser("list", help="List virtual environments")

    # ictfd runner
    ictfd_parser = subparsers.add_parser("ictfd", help="Run ictfd with provided arguments")
    ictfd_parser.add_argument("ictfd_args", nargs=argparse.REMAINDER, help="Arguments for ictfd")

    return parser

def main():
    init_main_env()
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "proj":
        if args.proj_command == "init":
            init_project(name=args.name, interactive=args.interactive)
        elif args.proj_command == "remove":
            remove_project(args.name)
        elif args.proj_command == "list":
            list_projects()
        else:
            print("[proj] Unknown project subcommand.")
    elif args.command == "run":
        run_script(args.path)
    elif args.command == "venv":
        if args.venv_command == "create":
            venv_command("create", getattr(args, "name", None))
        elif args.venv_command == "remove":
            venv_command("remove", getattr(args, "name", None))
        elif args.venv_command == "list":
            venv_command("list")
        else:
            print("[venv] Unknown venv subcommand.")
    elif args.command and args.command.startswith("ictfd"):
        ictfd_script = os.path.join(PRYZMA_PATH, "tools", "ictfd.py")
        if not os.path.exists(ictfd_script):
            print(f"[tools] ictfd not found")
            return

        subprocess.run([sys.executable, ictfd_script] + args.ictfd_args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

