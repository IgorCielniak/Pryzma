import argparse
import os
import sys
import json
import shutil
import subprocess
import requests
import zipfile
import io
from pathlib import Path

PRYZMA_PATH = os.path.abspath(os.path.dirname(__file__))
PROJECTS_PATH = os.path.abspath(os.path.join(PRYZMA_PATH, "projects"))
VENVS_PATH = os.path.abspath(os.path.join(PRYZMA_PATH, "venvs"))
CONFIG_PATHS = [
    os.path.abspath("./config.json"),
    os.path.expanduser("~/.pryzma/config.json")
]


PACKAGES_DIR = os.path.join(PRYZMA_PATH, "Pryzma-programming-language", "packages")


TEMPLATES = {
    "basic": {
        "description": "Basic Pryzma project",
        "files": {
            "main.pryzma": '# Your main script\n/main{\n    print "Hello, Pryzma!"\n}\n\n@main',
            "test.pryzma": '# Test script\n/main{\n    print "Running tests..."\n}\n\n@main',
            "requirements.txt": '# Add one package per line\n',
            "README.md": "# {project_name}\n\nA Pryzma project",
        }
    },
    "lib": {
        "description": "Library project template",
        "files": {
            "src/module.pryzma": "# Library module\n/greet{\n    return 'Hello, ' + args[0]\n}",
            "test.pryzma": '# Tests\nuse ./src/module.pryzma\n\nprint @module.greet("my name")',
            "requirements.txt": '# Add one package per line\n',
            "README.md": "# {project_name}\n\nA Pryzma library",
            "metadata.json": '{"name": "{project_name}", "version": "1.0.0", "files": ["src/module.pryzma", "tests/test_module.pryzma"], "author": "Your name", "description": "{project_name} - library written in Pryzma", "license": "MIT"}'
        }
    },
}


GITIGNORE_TEMPLATE = """
.gitignore
__pycache__/
*.swp
*.swo
"""


def load_config():
    for path in CONFIG_PATHS:
        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)

    print(f"[config] No config file found at {CONFIG_PATHS[0]} or {CONFIG_PATHS[1]}")
    return {}


def set_config_value(key, value, use_global=False):
    """Set a configuration value in either local or global config"""
    config_path = CONFIG_PATHS[1] if use_global else CONFIG_PATHS[0]

    os.makedirs(os.path.dirname(config_path), exist_ok=True)

    config = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
        except json.JSONDecodeError:
            print(f"[config] Warning: Existing config at {config_path} is invalid")

    if value.lower() == 'true':
        value = True
    elif value.lower() == 'false':
        value = False
    elif value.isdigit():
        value = int(value)
    elif value.replace('.', '', 1).isdigit():
        value = float(value)

    config[key] = value

    try:
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=4)
        print(f"[config] Set {key} = {value} in {'global' if use_global else 'local'} config")
        return True
    except Exception as e:
        print(f"[config] Error saving config: {e}")
        return False


def remove_config_key(key, use_global=False):
    """Remove a key from configuration"""
    config_path = CONFIG_PATHS[1] if use_global else CONFIG_PATHS[0]

    if not os.path.exists(config_path):
        print(f"[config] No {'global' if use_global else 'local'} config file found")
        return False

    try:
        with open(config_path, 'r') as f:
            config = json.load(f)

        if key not in config:
            print(f"[config] Key '{key}' not found in config")
            return False

        removed_value = config.pop(key)

        with open(config_path, 'w') as f:
            json.dump(config, f, indent=4)

        print(f"[config] Removed '{key}' (was: {removed_value})")
        return True

    except json.JSONDecodeError:
        print(f"[config] Error: Invalid JSON in config file")
        return False
    except Exception as e:
        print(f"[config] Error removing key: {e}")
        return False


def init_main_env():
    for path in [VENVS_PATH, PROJECTS_PATH]:
        if not os.path.exists(path):
            os.makedirs(path)
            print(f"[init] Created {path}")

def create_project_structure(project_path, template_name, project_name):
    """Create project files based on template"""
    if template_name not in TEMPLATES:
        print(f"[init] Unknown template '{template_name}'. Using 'basic' template.")
        template_name = "basic"
    
    template = TEMPLATES[template_name]
    
    print(f"[init] Creating project with '{template_name}' template")
    print(f"[init] {template['description']}")
    
    for rel_path, content in template["files"].items():
        rel_path = rel_path.replace("{project_name}", project_name)
        
        if "{project_name}" in content:
            content = content.replace("{project_name}", project_name)
        
        full_path = os.path.join(project_path, rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        
        with open(full_path, "w") as f:
            f.write(content)
        print(f"[init] Created {rel_path}")

    lib_entry = "src/module.pryzma"
    basic_entry = "main.pryzma"

    config = {
        "name": project_name,
        "type": template_name,
        "version": "1.0",
        "entry_point": f"{lib_entry if template_name == "lib" else basic_entry}",
        "description": TEMPLATES[template_name]["description"],
    }

    config_path = os.path.join(project_path, ".pryzma")
    with open(config_path, "w") as f:
        json.dump(config, f, indent=4)
    print(f"[init] Created .pryzma config at {config_path}")


def init_project(name=None, interactive=False, template="basic", use_git=False, create_gitignore=True):
    if interactive:
        print("[init] Interactive project creation:")
        name = input("Enter project name: ").strip()
        print("Available templates:")
        for tpl_name, tpl_info in TEMPLATES.items():
            print(f"  {tpl_name}: {tpl_info['description']}")
        template = input("Choose template (default: basic): ").strip() or "basic"
        if use_git:
            create_gitignore = input("Create a .gitignore (default: Yes): ").strip() or True

    if not name:
        print("[init] Project name is required.")
        return

    path = os.path.join(PROJECTS_PATH, name)
    if os.path.exists(path):
        print(f"[init] Project '{name}' already exists.")
        return

    os.makedirs(path)
    create_project_structure(path, template, name)
    print(f"[init] Created project '{name}' at {path}")

    if use_git:
        try:
            subprocess.run(["git", "init"], cwd=path, check=True)
            print(f"[init] Initialized empty Git repository in {path}")

            if create_gitignore:
                gitignore_path = os.path.join(path, ".gitignore")
                with open(gitignore_path, "w") as f:
                    f.write(GITIGNORE_TEMPLATE.strip() + "\n")
                print(f"[init] Created .gitignore at {gitignore_path}")

        except Exception as e:
            print(f"[git] Failed to initialize Git repo: {e}")

def remove_project(name):
    project_path = os.path.join(PROJECTS_PATH, name)

    if not os.path.exists(project_path):
        print(f"[remove] Project '{name}' does not exist.")
        return

    is_symlink = os.path.islink(project_path)
    original_path = None

    if is_symlink:
        original_path = os.path.realpath(project_path)
        message = f"[remove] Project '{name}' is a symlink to {original_path}\nDelete the symlink? (y/n): "
    else:
        message = f"[remove] Delete project '{name}' and all its contents? (y/n): "

    confirm = input(message).lower()
    if confirm != 'y':
        print("[remove] Cancelled.")
        return

    try:
        if is_symlink:
            os.unlink(project_path)
            print(f"[remove] Removed symlink to project '{name}'")
            print(f"[remove] Original files remain at: {original_path}")
        else:
            shutil.rmtree(project_path)
            print(f"[remove] Project '{name}' has been deleted.")
    except Exception as e:
        print(f"[error] Failed to delete project: {e}")


def list_projects(detailed=False):
    print("[list] Listing all projects...")
    if not os.path.exists(PROJECTS_PATH):
        print("[list] No projects directory found.")
        return

    projects = os.listdir(PROJECTS_PATH)
    if not projects:
        print("[list] No projects found.")
    else:
        for project in projects:
            project_path = os.path.join(PROJECTS_PATH, project)
            if detailed:
                config_path = os.path.join(project_path, ".pryzma")
                if os.path.exists(config_path):
                    try:
                        with open(config_path) as f:
                            config = json.load(f)
                        print(f" - {project} (v{config.get('version', '?.?.?')})")
                        print(f"   Type: {config.get('type', 'unknown')}")
                        print(f"   Path: {project_path}")
                        if "description" in config:
                            print(f"   Description: {config['description']}")
                        print()
                        continue
                    except json.JSONDecodeError:
                        pass
            print(f" - {project}")

def show_project_info(name):
    project_path = os.path.join(PROJECTS_PATH, name)
    if not os.path.exists(project_path):
        print(f"[info] Project '{name}' does not exist.")
        return

    config_path = os.path.join(project_path, ".pryzma")
    if os.path.exists(config_path):
        try:
            with open(config_path) as f:
                config = json.load(f)
            print(f"Project: {name}")
            print(f"Path: {project_path}")
            print(f"Type: {config.get('type', 'unknown')}")
            print(f"Version: {config.get('version', '?.?.?')}")
            if "description" in config:
                print(f"Description: {config['description']}")
            if "entry_point" in config:
                print(f"Entry point: {config['entry_point']}")
            return
        except json.JSONDecodeError:
            pass

    print(f"Basic project: {name}")
    print(f"Path: {project_path}")
    print("No additional project metadata found.")


def add_project(path):
    """Add an existing project by creating a symlink in the projects directory"""
    try:
        abs_path = os.path.abspath(path)

        if not os.path.isdir(abs_path):
            print(f"[add] Path '{abs_path}' is not a directory or doesn't exist")
            return False

        project_name = os.path.basename(abs_path.rstrip('/'))

        symlink_path = os.path.join(PROJECTS_PATH, project_name)

        if os.path.exists(symlink_path):
            print(f"[add] Project '{project_name}' already exists in projects directory")
            return False

        os.symlink(abs_path, symlink_path)
        print(f"[add] Created symlink to project '{project_name}' at {symlink_path}")
        return True

    except OSError as e:
        print(f"[add] Error creating symlink: {e}")
        return False
    except Exception as e:
        print(f"[add] Unexpected error: {e}")
        return False


def get_project_entry_point(project_name):
    project_path = os.path.join(PROJECTS_PATH, project_name)

    if not os.path.exists(project_path):
        print(f"[run] Project '{project_name}' does not exist.")
        return None

    if os.path.islink(project_path):
        project_path = os.path.realpath(project_path)

    config_path = os.path.join(project_path, ".pryzma")
    if not os.path.exists(config_path):
        print(f"[run] No .pryzma config found in project '{project_name}'")
        return None

    try:
        with open(config_path) as f:
            config = json.load(f)
        entry_point = config.get("entry_point")
        if not entry_point:
            print(f"[run] No entry_point defined in .pryzma config")
            return None
        return os.path.join(project_path, entry_point)
    except json.JSONDecodeError:
        print(f"[run] Invalid .pryzma config file")
        return None
    except Exception as e:
        print(f"[run] Error reading .pryzma config: {e}")
        return None


def run_project(name, debug=False):
    project_path = os.path.join(PROJECTS_PATH, name)

    config_path = os.path.join(project_path, ".pryzma")
    venv_path = None
    if os.path.exists(config_path):
        try:
            with open(config_path) as f:
                config = json.load(f)
                venv_path = config.get("venv")
        except json.JSONDecodeError:
            pass

    if venv_path and os.path.exists(venv_path):
        interpreter_path = venv_path
        print(f"[run] Using virtual environment at {venv_path}")
    else:
        config = load_config()
        interpreter_path = config.get("interpreter_path", "Pryzma-programming-language")

    entry_point = get_project_entry_point(name)
    if not entry_point:
        return False

    if not os.path.exists(entry_point):
        print(f"[run] Entry point '{entry_point}' not found")
        return False

    print(f"[run] Running project '{name}' entry point: {entry_point}")

    original_path = sys.path.copy()

    try:
        sys.path.append(os.path.abspath(interpreter_path))

        try:
            from Pryzma import PryzmaInterpreter
            interpreter = PryzmaInterpreter()
            if debug:
                interpreter.debug_interpreter(interpreter, entry_point, True, None)
            else:
                interpreter.interpret_file(entry_point)
        except ImportError as e:
            print(f"[error] Could not import Pryzma interpreter: {e}")
            return False
        except Exception as e:
            print(f"[error] Error running script: {e}")
            return False
    finally:
        sys.path = original_path

    return True


def install_dependencies(project_name):
    """Install project dependencies from requirements.txt"""
    project_path = os.path.join(PROJECTS_PATH, project_name)
    requirements_file = os.path.join(project_path, "requirements.txt")

    if not os.path.exists(requirements_file):
        print(f"[install] No requirements.txt found in project '{project_name}'")
        return False

    try:
        with open(requirements_file, 'r') as f:
            packages = [line.strip() for line in f if line.strip() and not line.startswith('#')]

        if not packages:
            print(f"[install] No dependencies found in requirements.txt")
            return True

        print(f"[install] Installing {len(packages)} dependencies for '{project_name}'...")

        for package in packages:
            print(f"[install] Installing {package}...")
            ppm_install(package)

        print("[install] Dependency installation complete")
        return True

    except Exception as e:
        print(f"[install] Error installing dependencies: {e}")
        return False


def venv_command(action, name=None, project_name=None):
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
            shutil.copy(os.path.join(interpreter_path, "Pryzma.py"), target_path)
        else:
            shutil.copy(interpreter_path, target_path)

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
    elif action == "link":
        venv_link_project(name, project_name)
    elif action == "unlink":
        venv_unlink_project(name)
    elif action == "run":
        print("[venv] Launching Pryzma interpreter...")
        sys.path.append(os.path.abspath(os.path.join(VENVS_PATH, name)))

        try:
            os.system("python " + os.path.join(os.path.join(VENVS_PATH, name), "Pryzma.py"))
        except Exception as e:
            print(f"[error] Error launching interpreter: {e}")


def venv_link_project(venv_name, project_name):
    venv_path = os.path.join(VENVS_PATH, venv_name)
    project_path = os.path.join(PROJECTS_PATH, project_name)

    if not os.path.exists(venv_path):
        print(f"[venv] Virtual environment '{venv_name}' does not exist")
        return False

    if not os.path.exists(project_path):
        print(f"[venv] Project '{project_name}' does not exist")
        return False

    config_path = os.path.join(project_path, ".pryzma")
    config = {}
    if os.path.exists(config_path):
        try:
            with open(config_path) as f:
                config = json.load(f)
        except json.JSONDecodeError:
            print("[venv] Warning: Could not parse existing .pryzma config")

    config["venv"] = venv_path

    try:
        with open(config_path, "w") as f:
            json.dump(config, f, indent=4)
        print(f"[venv] Linked virtual environment '{venv_name}' to project '{project_name}'")
        return True
    except Exception as e:
        print(f"[venv] Error saving config: {e}")
        return False


def venv_unlink_project(project_name):
    project_path = os.path.join(PROJECTS_PATH, project_name)

    if not os.path.exists(project_path):
        print(f"[venv] Project '{project_name}' does not exist")
        return False

    config_path = os.path.join(project_path, ".pryzma")
    config = {}
    if os.path.exists(config_path):
        try:
            with open(config_path) as f:
                config = json.load(f)
        except json.JSONDecodeError:
            print("[venv] Warning: Could not parse existing .pryzma config")

    config["venv"] = None

    try:
        with open(config_path, "w") as f:
            json.dump(config, f, indent=4)
        print(f"[venv] Unlinked virtual environment from project '{project_name}'")
        return True
    except Exception as e:
        print(f"[venv] Error saving config: {e}")
        return False


def run_script(path=None, debug=False):
    config = load_config()
    interpreter_path = config.get("interpreter_path", "Pryzma-programming-language")
    
    if not os.path.exists(os.path.join(interpreter_path, "Pryzma.py")):
        print(f"[run] Interpreter not found at '{interpreter_path}'")
        return

    if path:
        print(f"[run] Running Pryzma script at '{path}'...")
        sys.path.append(os.path.abspath(interpreter_path))

        try:
            from Pryzma import PryzmaInterpreter
            interpreter = PryzmaInterpreter()
            if debug:
                interpreter.debug_interpreter(interpreter, path, True, None)
            else:
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


def compile_script(path):
    config = load_config()
    interpreter_path = config.get("interpreter_path", "Pryzma-programming-language")

    if not os.path.exists(os.path.join(interpreter_path, "Pryzmac.py")):
        print(f"[run] Compiler not found at '{interpreter_path}'")
        return

    print("[run] Launching Pryzma compiler...")
    sys.path.append(os.path.abspath(interpreter_path))

    try:
        os.system("python " + os.path.join(interpreter_path, "Pryzmac.py") + " " + path)
    except Exception as e:
        print(f"[error] Error launching compiler: {e}")



def ppm_install(package_name):
    os.makedirs(PACKAGES_DIR, exist_ok=True)
    package_path = os.path.join(PACKAGES_DIR, package_name)

    if os.path.exists(package_path):
        print(f"Package '{package_name}' is already installed.")
        return

    # === PRIMARY SOURCE ===
    primary_url = f"http://igorcielniak.pythonanywhere.com/api/download/{package_name}"
    print(f"Trying to download {package_name} from primary source...")

    try:
        response = requests.get(primary_url, timeout=10)
        response.raise_for_status()

        print("Download succeeded. Extracting package...")
        with zipfile.ZipFile(io.BytesIO(response.content)) as zip_ref:
            zip_ref.extractall(package_path)
        print(f"{package_name} installed successfully from primary source.")
        return
    except Exception as e:
        print(f"Primary source failed: {e}")

    # === FALLBACK SOURCE ===
    print("Trying fallback source (GitHub)...")

    github_repo_url = "https://github.com/IgorCielniak/Pryzma-packages"
    clone_dir = os.path.join("/tmp", f"ppm_temp_{package_name}")

    try:
        subprocess.run(["git", "clone", "--depth=1", github_repo_url, clone_dir], check=True)

        package_folder = os.path.join(clone_dir, package_name)
        if not os.path.isdir(package_folder):
            raise FileNotFoundError(f"Package '{package_name}' not found in GitHub repo.")

        shutil.copytree(package_folder, package_path)
        print(f"{package_name} installed successfully from GitHub.")
    except Exception as e:
        print(f"Fallback source failed: {e}")
        print("Package installation failed from both sources.")
    finally:
        if os.path.exists(clone_dir):
            shutil.rmtree(clone_dir)


def ppm_list():
    if not os.path.isdir(PACKAGES_DIR):
        print("No packages installed.")
        return

    packages = os.listdir(PACKAGES_DIR)
    if not packages:
        print("No packages installed.")
        return

    print("Installed packages:")
    for pkg in packages:
        print(f"- {pkg}")


def ppm_remove(package_name):
    package_path = os.path.join(PACKAGES_DIR, package_name)

    if os.path.isdir(package_path):
        shutil.rmtree(package_path)
        print(f"Package '{package_name}' removed.")
    else:
        print(f"Package '{package_name}' not found.")


def ppm_info(package_name):
    metadata_path = os.path.join(PACKAGES_DIR, package_name, "metadata.json")

    if not os.path.isfile(metadata_path):
        print(f"No metadata found for package '{package_name}'.")
        return

    try:
        with open(metadata_path, "r") as f:
            data = json.load(f)

        print("Package Info:")
        for key, value in data.items():
            print(f"{key.capitalize()}: {value}")
    except Exception as e:
        print(f"Error reading metadata: {e}")

def ppm_update_package(package_name):
    print(f"Updating {package_name}...")
    shutil.rmtree(os.path.join(PACKAGES_DIR, package_name))
    ppm_install(package_name)
    print(f"Updated {package_name} successfully.\n")

def ppm_update_all():
    if not Path(PACKAGES_DIR).exists():
        print("No packages installed.")
        return
    
    for pkg in Path(PACKAGES_DIR).iterdir():
        if pkg.is_dir():
            ppm_update_package(pkg.name)


def build_parser():
    parser = argparse.ArgumentParser(prog="pryzma-manager", description="Manage Pryzma projects and environments")
    subparsers = parser.add_subparsers(dest="command")

    # Project group
    proj_parser = subparsers.add_parser("proj", help="Project management commands")
    proj_subparsers = proj_parser.add_subparsers(dest="proj_command")

    proj_init = proj_subparsers.add_parser("init", help="Initialize a new Pryzma project")
    proj_init.add_argument("name", nargs="?", help="Project name")
    proj_init.add_argument("-i", "--interactive", action="store_true", help="Interactive mode")
    proj_init.add_argument("-t", "--template", choices=list(TEMPLATES.keys()), default="basic",
                          help="Project template to use")
    proj_init.add_argument("-g", "--git", action="store_true", help="Use git")
    proj_init.add_argument("-gi", "--git-ignore", action="store_true", help="Create a default .gitignore")

    proj_remove = proj_subparsers.add_parser("remove", help="Remove a project")
    proj_remove.add_argument("name", help="Project name")

    proj_list = proj_subparsers.add_parser("list", help="List all Pryzma projects")
    proj_list.add_argument("-d", "--detailed", action="store_true", help="Show detailed project information")

    proj_info = proj_subparsers.add_parser("info", help="Show project information")
    proj_info.add_argument("name", help="Project name")

    proj_add = proj_subparsers.add_parser("add", help="Add an existing project by creating a symlink")
    proj_add.add_argument("path", help="Path to the existing project directory")

    proj_run = proj_subparsers.add_parser("run", help="Run the project's entry point")
    proj_run.add_argument("name", help="Project name")
    proj_run.add_argument("-d", "--debug", action="store_true", help="Run in debug mode")

    proj_install = proj_subparsers.add_parser("install", help="Install project dependencies")
    proj_install.add_argument("name", help="Project name")

    # Run command
    run_parser = subparsers.add_parser("run", help="Run a Pryzma script")
    run_parser.add_argument("path", nargs="?", help="Path to .pryzma script")
    run_parser.add_argument("-d", "--debug", action="store_true", help="Flag used to run in debug mode")

    # Compile command
    compile_parser = subparsers.add_parser("compile", help="Compile a Pryzma script")
    compile_parser.add_argument("path", nargs="?", help="Path to .pryzma script")

    # Venv group
    venv_parser = subparsers.add_parser("venv", help="Manage Pryzma virtual environments")
    venv_subparsers = venv_parser.add_subparsers(dest="venv_command")

    venv_create = venv_subparsers.add_parser("create", help="Create a virtual environment")
    venv_create.add_argument("name", help="Name of the virtual environment")

    venv_create = venv_subparsers.add_parser("remove", help="Remove a virtual environment")
    venv_create.add_argument("name", help="Name of the virtual environment")

    venv_subparsers.add_parser("list", help="List virtual environments")

    venv_link = venv_subparsers.add_parser("link", help="Link a virtual environment to a project")
    venv_link.add_argument("venv_name", help="Name of the virtual environment")
    venv_link.add_argument("project_name", help="Name of the project to link to")

    venv_unlink = venv_subparsers.add_parser("unlink", help="Unlink a virtual environment from a project")
    venv_unlink.add_argument("project_name", help="Name of the project to unlink")

    venv_run = venv_subparsers.add_parser("run", help="Run the interpreter from a give venv")
    venv_run.add_argument("venv_name", help="Name of the virtual environment")

    # ictfd runner
    ictfd_parser = subparsers.add_parser("ictfd", help="Run ictfd with provided arguments")
    ictfd_parser.add_argument("ictfd_args", nargs=argparse.REMAINDER, help="Arguments for ictfd")

    #ppm parser
    ppm = subparsers.add_parser("ppm")
    ppm.add_argument("action", choices=["install", "list", "remove", "info", "update"])
    ppm.add_argument("package", nargs="?")

    # Config command
    config_parser = subparsers.add_parser("config", help="Manage configuration")
    config_subparsers = config_parser.add_subparsers(dest="config_action")
    show_parser = config_subparsers.add_parser("show", help="Show config")

    set_parser = config_subparsers.add_parser("set", help="Set configuration value")
    set_parser.add_argument("key", help="Configuration key to set")
    set_parser.add_argument("value", help="Value to set")
    set_parser.add_argument("--global", action="store_true", help="Save to global config")

    remove_parser = config_subparsers.add_parser("remove", help="Remove a configuration key")
    remove_parser.add_argument("key", help="Key to remove")
    remove_parser.add_argument("--global", action="store_true", help="Remove from global config")

    return parser

def main():
    init_main_env()
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "proj":
        if args.proj_command == "init":
            init_project(name=args.name, interactive=args.interactive, template=args.template, use_git=args.git, create_gitignore=args.git_ignore)
        elif args.proj_command == "remove":
            remove_project(args.name)
        elif args.proj_command == "list":
            list_projects(args.detailed)
        elif args.proj_command == "info":
            show_project_info(args.name)
        elif args.proj_command == "add":
            add_project(args.path)
        elif args.proj_command == "run":
            run_project(args.name, args.debug)
        elif args.proj_command == "install":
            install_dependencies(args.name)
        else:
            print("[proj] Unknown project subcommand.")
    elif args.command == "run":
        run_script(args.path, args.debug)
    elif args.command == "compile":
        compile_script(args.path)
    elif args.command == "venv":
        if args.venv_command == "create":
            venv_command("create", getattr(args, "name", None))
        elif args.venv_command == "remove":
            venv_command("remove", getattr(args, "name", None))
        elif args.venv_command == "list":
            venv_command("list")
        elif args.venv_command == "link":
            venv_command("link", args.venv_name, args.project_name)
        elif args.venv_command == "unlink":
            venv_command("unlink", args.project_name)
        elif args.venv_command == "run":
            venv_command("run", args.venv_name)
        else:
            print("[venv] Unknown venv subcommand.")
    elif args.command == "ppm":
        if args.action == "install" and args.package:
            ppm_install(args.package)
        elif args.action == "list":
            ppm_list()
        elif args.action == "remove" and args.package:
            ppm_remove(args.package)
        elif args.action == "info" and args.package:
            ppm_info(args.package)
        elif args.action == "update":
            if args.package:
                ppm_update_package(args.package)
            else:
                ppm_update_all()
        else:
            print("Invalid command or missing package name.")
    elif args.command == "config":
        if args.config_action == "show":
            config = load_config()
            print("Current configuration:")
            for key, value in config.items():
                print(f"{key}: {value}")
        elif args.config_action == "set":
            set_config_value(args.key, args.value, getattr(args, "global", False))
        elif args.config_action == "remove":
            remove_config_key(args.key, getattr(args, "global", False))
        else:
            print("[config] Unknown config subcommand.")
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

