import argparse
import os
import re
import sys
import json
import shutil
import subprocess
import requests
import zipfile
import io
import importlib
from collections import OrderedDict
from pathlib import Path

PRYZMA_PATH = os.path.abspath(os.path.dirname(__file__))
PROJECTS_PATH = os.path.abspath(os.path.join(PRYZMA_PATH, "projects"))
VENVS_PATH = os.path.abspath(os.path.join(PRYZMA_PATH, "venvs"))
CONFIG_PATHS = [
    os.path.join(PRYZMA_PATH, "config.json"),
    os.path.expanduser("~/.pryzma/config.json")
]


PACKAGES_DIR = os.path.join(PRYZMA_PATH, "Pryzma-programming-language", "packages")
PLUGINS_DIR = os.path.abspath(os.path.join(PRYZMA_PATH, "plugins"))
PLUGIN_DISABLED_PREFIX = "DISABLED_"

TEMPLATES = {
    "basic": {
        "description": "Basic Pryzma project",
        "files": {
            "main.pryzma": '# Your main script\n/main{\n    print "Hello, Pryzma!"\n}\n\n@main',
            "requirements.txt": '# Add one package per line\n',
            "README.md": "# {project_name}\n\nA Pryzma project",
            "tests/test.test": f"python {os.path.join(PRYZMA_PATH, 'Pryzma-programming-language/Pryzma.py')} main.pryzma",
            "tests/test.expected": "Hello, Pryzma!",
            "notes": ""
        }
    },
    "lib": {
        "description": "Library project template",
        "files": {
            "src/module.pryzma": "# Library module\n/greet{\n    return 'Hello, ' + args[0]\n}",
            "requirements.txt": '# Add one package per line\n',
            "README.md": "# {project_name}\n\nA Pryzma library",
            "metadata.json": '{"name": "{project_name}", "version": "1.0.0", "files": ["src/module.pryzma", "tests/test.pryzma", "tests/test.test", "tests/test.expected"], "author": "Your name", "description": "{project_name} - library written in Pryzma", "license": "MIT"}',
            "tests/test.test": f"python {os.path.join(PRYZMA_PATH, 'Pryzma-programming-language/Pryzma.py')} tests/test.pryzma",
            "tests/test.pryzma": '# Tests\nuse ./src/module.pryzma\n\nprint @module.greet("my name")',
            "tests/test.expected": "Hello, my name",
            "notes": ""
        }
    },
}


GITIGNORE_TEMPLATE = """
.gitignore
*__pycache__
notes
*.swp
*.swo
"""

def load_plugins(main_parser):
    """Load all enabled plugins that have valid metadata and command files"""
    if not os.path.exists(PLUGINS_DIR):
        print("[plugins] No plugins directory found")
        return

    if not any(isinstance(action, argparse._SubParsersAction)
               for action in main_parser._actions):
        main_parser.add_subparsers(title='commands')

    subparsers_action = None
    for action in main_parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            subparsers_action = action
            break

    if not subparsers_action:
        print("[plugins] Warning: Couldn't create command group for plugins")
        return

    loaded_count = 0
    skipped_count = 0

    for plugin_name in sorted(os.listdir(PLUGINS_DIR)):
        if plugin_name.startswith(PLUGIN_DISABLED_PREFIX):
            skipped_count += 1
            continue

        plugin_dir = os.path.join(PLUGINS_DIR, plugin_name)
        metadata_path = os.path.join(plugin_dir, "metadata.json")
        commands_path = os.path.join(plugin_dir, "commands.py")

        if not os.path.exists(metadata_path):
            print(f"[plugins] Skipping '{plugin_name}': missing metadata.json")
            skipped_count += 1
            continue

        if not os.path.exists(commands_path):
            print(f"[plugins] Skipping '{plugin_name}': missing commands.py")
            skipped_count += 1
            continue

        try:
            with open(metadata_path) as f:
                metadata = json.load(f)

            if not isinstance(metadata, dict):
                print(f"[plugins] Skipping '{plugin_name}': invalid metadata format")
                skipped_count += 1
                continue

            spec = importlib.util.spec_from_file_location(
                f"plugins.{plugin_name}", commands_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            if hasattr(module, "register_commands"):
                module.register_commands(subparsers_action)

                version = metadata.get("version", "?.?.?")
                print(f"[plugins] Loaded {plugin_name} v{version}")
                loaded_count += 1
            else:
                print(f"[plugins] Skipping '{plugin_name}': no register_commands()")
                skipped_count += 1

        except json.JSONDecodeError:
            print(f"[plugins] Skipping '{plugin_name}': invalid metadata.json")
            skipped_count += 1
        except ImportError as e:
            print(f"[plugins] Failed to import '{plugin_name}': {str(e)}")
            skipped_count += 1
        except Exception as e:
            print(f"[plugins] Error loading '{plugin_name}': {str(e)}")
            skipped_count += 1

    print(f"[plugins] Loaded {loaded_count} plugins, skipped {skipped_count}")

def list_plugins(show_all=False):
    """List all available plugins"""
    if not os.path.exists(PLUGINS_DIR):
        print("[plugins] No plugins directory found")
        return []

    plugins = []
    for name in sorted(os.listdir(PLUGINS_DIR)):
        disabled = name.startswith(PLUGIN_DISABLED_PREFIX)
        real_name = name[len(PLUGIN_DISABLED_PREFIX):] if disabled else name
        plugin_path = os.path.join(PLUGINS_DIR, name, "commands.py")

        if os.path.exists(plugin_path):
            plugins.append({
                "name": real_name,
                "disabled": disabled,
                "path": plugin_path
            })

    if not plugins:
        print("[plugins] No plugins installed")
        return []

    print("Available plugins:")
    for plugin in plugins:
        status = "DISABLED" if plugin["disabled"] else "ENABLED"
        print(f" - {plugin['name']} [{status}]")

    return plugins

def toggle_plugin(plugin_name, enable=True):
    """Enable or disable a plugin"""
    plugin_dir = os.path.join(PLUGINS_DIR, plugin_name)
    disabled_dir = os.path.join(PLUGINS_DIR, f"{PLUGIN_DISABLED_PREFIX}{plugin_name}")

    if enable:
        if os.path.exists(disabled_dir):
            os.rename(disabled_dir, plugin_dir)
            print(f"Enabled plugin: {plugin_name}")
            return True
    else:
        if os.path.exists(plugin_dir):
            os.rename(plugin_dir, disabled_dir)
            print(f"Disabled plugin: {plugin_name}")
            return True

    print(f"Plugin not found: {plugin_name}")
    return False

def show_plugin_info(plugin_name):
    """Show information from plugin's metadata.json"""
    for prefix in ("", PLUGIN_DISABLED_PREFIX):
        plugin_dir = os.path.join(PLUGINS_DIR, f"{prefix}{plugin_name}")
        metadata_path = os.path.join(plugin_dir, "metadata.json")

        if os.path.exists(metadata_path):
            try:
                with open(metadata_path) as f:
                    metadata = json.load(f)

                print(f"\nPlugin: {plugin_name}")
                print(f"Status: {'Disabled' if prefix else 'Enabled'}")
                print("-" * 40)

                for field in ["author", "version", "description", "license"]:
                    if field in metadata:
                        print(f"{field.capitalize():<12}: {metadata[field]}")

                custom_fields = set(metadata.keys()) - {"author", "version", "description", "license"}
                if custom_fields:
                    print("\nAdditional Info:")
                    for field in sorted(custom_fields):
                        print(f"{field.capitalize():<12}: {metadata[field]}")

                return True

            except json.JSONDecodeError:
                print(f"Error: Invalid metadata.json in {plugin_name}")
                return False
            except Exception as e:
                print(f"Error reading plugin: {str(e)}")
                return False

    print(f"Plugin not found: {plugin_name}")
    return False

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
    config = load_config()
    if not "pryzma_path" in config:
        set_config_value("pryzma_path", os.path.abspath(os.path.dirname(__file__)))
        set_config_value("pryzma_path", os.path.abspath(os.path.dirname(__file__)), True)

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

    config_path = os.path.join(project_path, "pryzma.json")
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
        use_git = False if input("Use git? (y/n default yes):").strip() != "y" or "yes" else True
        if use_git:
            create_gitignore = False if input("Create a .gitignore (y/n default: yes): ").strip() != "y" or "yes" else True

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
    if name == ".":
        project_path = os.getcwd()
    else:
        project_path = os.path.join(PROJECTS_PATH, name)

    name = os.path.basename(project_path)

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
                config_path = os.path.join(project_path, "pryzma.json")
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
    if name == ".":
        project_path = os.getcwd()
    else:
        project_path = os.path.join(PROJECTS_PATH, name)

    name = os.path.basename(project_path)

    if not os.path.exists(project_path):
        print(f"[info] Project '{name}' does not exist.")
        return

    config_path = os.path.join(project_path, "pryzma.json")
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
    if project_name == ".":
        project_path = os.getcwd()
    else:
        project_path = os.path.join(PROJECTS_PATH, project_name)

    project_name = os.path.basename(project_path)

    if not os.path.exists(project_path):
        print(f"[run] Project '{project_name}' does not exist.")
        return None

    if os.path.islink(project_path):
        project_path = os.path.realpath(project_path)

    config_path = os.path.join(project_path, "pryzma.json")
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
    if name == ".":
        project_path = os.getcwd()
    else:
        project_path = os.path.join(PROJECTS_PATH, name)

    name = os.path.basename(project_path)

    config_path = os.path.join(project_path, "pryzma.json")
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

def test_project(args):
    if args.proj_name == ".":
        project_path = os.getcwd()
    else:
        project_path = os.path.join(PROJECTS_PATH, args.proj_name)

    name = os.path.basename(project_path)

    test_script = os.path.join(PRYZMA_PATH, 'tools', 'test.py')

    if not os.path.exists(project_path):
        print(f"Error: Project directory {project_path} does not exist")
        sys.exit(1)

    if not os.path.exists(test_script):
        print(f"Error: Test script {test_script} does not exist")
        sys.exit(1)

    os.chdir(project_path)
    os.system(f"python {test_script}")

def build_project(args):
    if args.proj_name == ".":
        project_path = os.getcwd()
    else:
        project_path = os.path.join(PROJECTS_PATH, args.proj_name)

    name = os.path.basename(project_path)

    if not os.path.exists(project_path):
        print(f"Error: Project directory {project_path} does not exist")
        sys.exit(1)

    project_config = os.path.join(project_path, "pryzma.json")
    if not os.path.exists(project_config):
        print(f"[build] Missing pryzma.json in {project_path}")
        sys.exit(1)

    with open(project_config) as file:
        content = json.load(file)

    entry_point = os.path.join(project_path, content["entry_point"])
    if not os.path.exists(entry_point):
        print(f"[build] Entry point '{entry_point}' does not exist")
        sys.exit(1)

    resolution = resolve_pryzma_dependencies(entry_point, project_path)

    # If auto-fetch requested, try to fetch missing Pryzma package dependencies via ppm
    auto_fetch = getattr(args, 'auto_fetch', False)
    if auto_fetch and resolution.get("missing"):
        def infer_package_name_from_reference(ref):
            if not ref:
                return None
            normalized = ref.replace('\\', '/').strip().strip('"\'')
            normalized = normalized.lstrip('@')
            if '::' in normalized:
                return normalized.split('::', 1)[0]
            if '/' in normalized or normalized.startswith('.') or normalized.startswith('/'):
                return None
            return normalized

        missing_before = list(resolution.get("missing", []))
        for issue in missing_before:
            pkg = infer_package_name_from_reference(issue.get("target"))
            if pkg:
                print(f"[build] Auto-fetching package '{pkg}' for missing reference '{issue.get('target')}'")
                try:
                    ppm_install(pkg)
                except Exception as e:
                    print(f"[build] Failed to auto-fetch package '{pkg}': {e}")

        # re-resolve after attempting installs
        resolution = resolve_pryzma_dependencies(entry_point, project_path)

    build_dir = os.path.join(project_path, "build")
    os.makedirs(build_dir, exist_ok=True)

    manifest_path = os.path.join(build_dir, "dependency_manifest.json")
    manifest_payload = {
        "entry_point": entry_point,
        "ordered_files": resolution["ordered"],
        "missing": resolution["missing"],
        "cycles": resolution["cycles"],
    }

    if resolution["missing"]:
        print("[build] Warning: unresolved dependencies detected:")
        for issue in resolution["missing"]:
            rel = os.path.relpath(issue["source"], project_path)
            print(f"  - {issue['target']} referenced in {rel}:{issue['line']} ({issue['type']})")

    if resolution["cycles"]:
        print("[build] Warning: dependency cycles detected:")
        for cycle in resolution["cycles"]:
            printable = " -> ".join([os.path.relpath(node, project_path) for node in cycle])
            print(f"  - {printable}")

    bundler = PryzmaSourceBundler(project_path)
    bundled_source = bundler.bundle(entry_point)

    manifest_payload["bundled_modules"] = bundler.module_metadata
    with open(manifest_path, "w", encoding="utf-8") as manifest_file:
        json.dump(manifest_payload, manifest_file, indent=4)

    with open(os.path.join(os.path.dirname(__file__), "minimal.py")) as file:
        py_template = file.read()

    runner = f"""
EMBEDDED_SOURCE = {bundled_source!r}


if __name__ == "__main__":
    interpreter = PryzmaInterpreter()
    interpreter.file_path = "<embedded>"
    interpreter.variables["__file__"] = "<embedded>"
    interpreter.pre_interpret(EMBEDDED_SOURCE)
    """

    build = py_template + runner

    out_name = os.path.join(build_dir, f"{name}_generated.py")
    with open(out_name, "w") as out_file:
        out_file.write(build)

    print(f"Generated Python written to: {out_name}")

    os.system(f"nuitka {out_name}")


def build_file(file_path, auto_fetch=False):
    entry_point = os.path.abspath(file_path)

    if not os.path.exists(entry_point):
        print(f"[build] File '{entry_point}' does not exist")
        sys.exit(1)

    project_path = os.path.dirname(entry_point) or os.getcwd()

    resolution = resolve_pryzma_dependencies(entry_point, project_path)

    # Optionally attempt to auto-fetch missing Pryzma package dependencies via ppm
    if auto_fetch and resolution.get("missing"):
        def infer_package_name_from_reference(ref):
            if not ref:
                return None
            normalized = ref.replace('\\', '/').strip().strip('"\'')
            normalized = normalized.lstrip('@')
            if '::' in normalized:
                return normalized.split('::', 1)[0]
            if '/' in normalized or normalized.startswith('.') or normalized.startswith('/'):
                return None
            return normalized

        missing_before = list(resolution.get("missing", []))
        for issue in missing_before:
            pkg = infer_package_name_from_reference(issue.get("target"))
            if pkg:
                print(f"[build] Auto-fetching package '{pkg}' for missing reference '{issue.get('target')}'")
                try:
                    ppm_install(pkg)
                except Exception as e:
                    print(f"[build] Failed to auto-fetch package '{pkg}': {e}")

        # re-resolve after attempting installs
        resolution = resolve_pryzma_dependencies(entry_point, project_path)

    build_dir = os.path.join(project_path, "build")
    os.makedirs(build_dir, exist_ok=True)

    manifest_path = os.path.join(build_dir, "dependency_manifest.json")
    manifest_payload = {
        "entry_point": entry_point,
        "ordered_files": resolution["ordered"],
        "missing": resolution["missing"],
        "cycles": resolution["cycles"],
    }

    if resolution["missing"]:
        print("[build] Warning: unresolved dependencies detected:")
        for issue in resolution["missing"]:
            rel = os.path.relpath(issue["source"], project_path)
            print(f"  - {issue['target']} referenced in {rel}:{issue['line']} ({issue['type']})")

    if resolution["cycles"]:
        print("[build] Warning: dependency cycles detected:")
        for cycle in resolution["cycles"]:
            printable = " -> ".join([os.path.relpath(node, project_path) for node in cycle])
            print(f"  - {printable}")

    bundler = PryzmaSourceBundler(project_path)
    bundled_source = bundler.bundle(entry_point)

    manifest_payload["bundled_modules"] = bundler.module_metadata
    with open(manifest_path, "w", encoding="utf-8") as manifest_file:
        json.dump(manifest_payload, manifest_file, indent=4)

    with open(os.path.join(os.path.dirname(__file__), "minimal.py")) as file:
        py_template = file.read()

    runner = f"""
EMBEDDED_SOURCE = {bundled_source!r}


if __name__ == "__main__":
    interpreter = PryzmaInterpreter()
    interpreter.file_path = "<embedded>"
    interpreter.variables["__file__"] = "<embedded>"
    interpreter.pre_interpret(EMBEDDED_SOURCE)
    """

    build = py_template + runner

    base_name = os.path.splitext(os.path.basename(entry_point))[0]
    out_name = os.path.join(build_dir, f"{base_name}_generated.py")
    with open(out_name, "w") as out_file:
        out_file.write(build)

    print(f"Generated Python written to: {out_name}")

    os.system(f"nuitka {out_name}")


def install_dependencies(project_name):
    if project_name == ".":
        project_path = os.getcwd()
    else:
        project_path = os.path.join(PROJECTS_PATH, project_name)

    project_name = os.path.basename(project_path)

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


def _strip_inline_comment(line):
    if "//" in line:
        return line.split("//", 1)[0]
    return line


def _sanitize_reference_fragment(fragment):
    if not fragment:
        return ""

    fragment = _strip_inline_comment(fragment).strip()

    stop_markers = [
        " with ",
        " as ",
        " import ",
        " => ",
        " = ",
        " {",
        " (",
        " [",
    ]

    for marker in stop_markers:
        idx = fragment.find(marker)
        if idx != -1:
            fragment = fragment[:idx]
            break

    if " " in fragment:
        fragment = fragment.split()[0]

    return fragment.strip().strip(';,"\'')


FUNCTION_DEF_PATTERN = re.compile(r'^/([^\s{]+)', re.MULTILINE)


def parse_pryzma_directives(file_path):
    directives = []

    try:
        with open(file_path, "r", encoding="utf-8") as source:
            for idx, raw_line in enumerate(source, start=1):
                stripped = raw_line.strip()
                if not stripped:
                    continue

                normalized = _strip_inline_comment(raw_line).strip()
                if not normalized:
                    continue

                if normalized.startswith("#insert"):
                    fragment = _sanitize_reference_fragment(normalized[len("#insert"):])
                    if fragment:
                        directives.append({"type": "insert", "target": fragment, "line": idx})
                elif normalized.startswith("use "):
                    fragment = _sanitize_reference_fragment(normalized[4:])
                    if fragment:
                        directives.append({"type": "use", "target": fragment, "line": idx})
    except FileNotFoundError:
        pass

    return directives


def parse_use_statement(line):
    normalized = _strip_inline_comment(line).strip().rstrip(";")
    if not normalized.lower().startswith("use "):
        return None

    remainder = normalized[4:].strip()
    tokens = remainder.split()

    target_tokens = []
    directives_tokens = []
    alias = None
    i = 0
    while i < len(tokens):
        token = tokens[i]
        lower = token.lower()
        if lower == "with":
            i += 1
            buffer = []
            while i < len(tokens) and tokens[i].lower() != "as":
                buffer.append(tokens[i])
                i += 1
            directives_tokens.extend(buffer)
            continue
        if lower == "as":
            i += 1
            if i < len(tokens):
                alias = tokens[i].strip('.,"\'')
                i += 1
            continue
        target_tokens.append(token)
        i += 1

    target = " ".join(target_tokens).strip().strip('"\'')
    directives = {token.strip(',').lower() for token in directives_tokens if token.strip(',')}

    return {
        "target": target,
        "alias": alias,
        "directives": directives,
    }


def _prefix_module_functions(source, alias):
    if not alias:
        return source

    def _replace(match):
        name = match.group(1).strip()
        if name.startswith(f"{alias}."):
            return f"/{name}"
        return f"/{alias}.{name}"

    return FUNCTION_DEF_PATTERN.sub(_replace, source)


class PryzmaSourceBundler:
    def __init__(self, project_root):
        self.project_root = os.path.realpath(project_root)
        self._module_sources = OrderedDict()
        self._processing = set()
        self._module_metadata = []

    def bundle(self, entry_path):
        entry_body = self._process_file(entry_path)
        combined_parts = []

        for idx, ((module_path, alias_key, _), module_source) in enumerate(self._module_sources.items(), start=1):
            header = f"// [bundle] module {idx}: {alias_key or os.path.basename(module_path)}\n"
            combined_parts.append(header)
            combined_parts.append(module_source.rstrip() + "\n")

        combined_parts.append(entry_body)
        return "\n".join(part for part in combined_parts if part)

    def _process_file(self, file_path):
        real_path = os.path.realpath(file_path)
        if real_path in self._processing:
            print(f"[bundle] Cycle detected for {real_path}, skipping nested include")
            return ""

        try:
            with open(real_path, "r", encoding="utf-8") as source:
                lines = source.readlines()
        except FileNotFoundError:
            print(f"[bundle] Missing file during bundling: {file_path}")
            return ""

        self._processing.add(real_path)
        output = []
        base_dir = os.path.dirname(real_path)

        for raw_line in lines:
            stripped = _strip_inline_comment(raw_line).strip()
            if stripped.startswith("use "):
                parsed = parse_use_statement(raw_line)
                if not parsed or not parsed["target"]:
                    continue

                resolved = resolve_pryzma_reference(parsed["target"], base_dir, self.project_root)
                if not resolved:
                    print(f"[bundle] Unable to resolve module '{parsed['target']}' referenced in {real_path}")
                    continue

                nan_flag = ("#nan" in parsed["directives"]) or ("nan" in parsed["directives"])
                alias = parsed["alias"]
                if not nan_flag:
                    alias = alias or os.path.splitext(os.path.basename(resolved))[0]
                else:
                    alias = parsed["alias"]

                self._include_module(resolved, alias, nan_flag)
                continue

            if stripped.startswith("#insert"):
                reference = _sanitize_reference_fragment(stripped[len("#insert"):])
                resolved = resolve_pryzma_reference(reference, base_dir, self.project_root)
                if not resolved:
                    print(f"[bundle] Unable to resolve insert '{reference}' in {real_path}")
                    continue
                output.append(self._process_file(resolved))
                continue

            output.append(raw_line)

        self._processing.remove(real_path)
        return "".join(output)

    def _include_module(self, module_path, alias, nan_flag):
        real_module_path = os.path.realpath(module_path)
        key = (real_module_path, alias or "", nan_flag)
        if key in self._module_sources:
            return

        module_body = self._process_file(real_module_path)
        if not nan_flag:
            effective_alias = alias or os.path.splitext(os.path.basename(real_module_path))[0]
            module_body = _prefix_module_functions(module_body, effective_alias)

        self._module_sources[key] = module_body
        self._module_metadata.append({
            "path": real_module_path,
            "alias": alias,
            "nan": nan_flag,
        })

    @property
    def module_metadata(self):
        return list(self._module_metadata)


def _resolve_package_reference(reference):
    if not reference:
        return None

    normalized = reference.strip().strip('"\'')
    normalized = normalized.lstrip("@")

    if not normalized:
        return None

    if normalized.startswith(".") or "/" in normalized or "\\" in normalized:
        return None

    package_relative = None
    if "::" in normalized:
        parts = [part.strip() for part in normalized.split("::") if part.strip()]
        if not parts:
            return None
        file_name = parts[-1]
        folder = os.path.join(*parts[:-1]) if len(parts) > 1 else ""
        package_relative = os.path.join(folder, f"{file_name}.pryzma") if folder else f"{file_name}.pryzma"
    else:
        package_relative = os.path.join(normalized, f"{normalized}.pryzma")

    candidate = os.path.join(PACKAGES_DIR, package_relative)
    if os.path.isfile(candidate):
        return candidate

    if candidate.endswith(".pryzma"):
        alt_candidate = candidate[:-7] + ".prz"
        if os.path.isfile(alt_candidate):
            return alt_candidate

    return None


def resolve_pryzma_reference(reference, current_dir, project_root):
    if not reference:
        return None

    normalized = reference.replace("\\", "/").strip().strip('"\'')
    candidates = [normalized]
    if not normalized.endswith(".pryzma"):
        candidates.append(f"{normalized}.pryzma")

    project_root = os.path.realpath(project_root)
    current_dir = os.path.realpath(current_dir) if current_dir else None

    search_roots = []
    if os.path.isabs(normalized):
        search_roots.append("")
    else:
        if current_dir:
            search_roots.append(current_dir)
        search_roots.append(project_root)
        src_root = os.path.join(project_root, "src")
        if os.path.isdir(src_root):
            search_roots.append(src_root)

    for root in search_roots:
        for candidate in candidates:
            candidate_path = os.path.normpath(os.path.join(root, candidate)) if root else os.path.normpath(candidate)
            if os.path.isfile(candidate_path):
                return candidate_path

    package_candidate = _resolve_package_reference(reference)
    if package_candidate and os.path.isfile(package_candidate):
        return package_candidate

    return None


def resolve_pryzma_dependencies(entry_path, project_root):
    visited = set()
    ordered = []
    graph = {}
    missing = []
    cycles = []

    def visit(path, trail):
        real_path = os.path.realpath(path)

        if real_path in trail:
            cycle_start = trail.index(real_path)
            cycles.append(trail[cycle_start:] + [real_path])
            return

        if real_path in visited:
            return

        visited.add(real_path)
        ordered.append(real_path)
        graph[real_path] = []

        directives = parse_pryzma_directives(real_path)
        base_dir = os.path.dirname(real_path)

        for directive in directives:
            resolved = resolve_pryzma_reference(directive["target"], base_dir, project_root)
            if not resolved:
                missing.append({
                    "source": real_path,
                    "target": directive["target"],
                    "line": directive["line"],
                    "type": directive["type"],
                })
                continue

            graph[real_path].append(resolved)
            visit(resolved, trail + [real_path])

    visit(entry_path, [])

    return {
        "ordered": ordered,
        "graph": graph,
        "missing": missing,
        "cycles": cycles,
    }
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
    if project_name == ".":
        project_path = os.getcwd()
    else:
        project_path = os.path.join(PROJECTS_PATH, project_name)

    project_name = os.path.basename(project_path)

    if not os.path.exists(venv_path):
        print(f"[venv] Virtual environment '{venv_name}' does not exist")
        return False

    if not os.path.exists(project_path):
        print(f"[venv] Project '{project_name}' does not exist")
        return False

    config_path = os.path.join(project_path, "pryzma.json")
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
    if project_name == ".":
        project_path = os.getcwd()
    else:
        project_path = os.path.join(PROJECTS_PATH, project_name)

    project_name = os.path.basename(project_path)

    if not os.path.exists(project_path):
        print(f"[venv] Project '{project_name}' does not exist")
        return False

    config_path = os.path.join(project_path, "pryzma.json")
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

    # === MIRRORS / PRIMARY SOURCES ===
    # Mirrors can be configured in the user's local config under the key 'ppm_mirrors'
    # They should be base URLs that accept /download/<package_name>

    def get_ppm_mirrors():
        cfg = load_config()
        mirrors = cfg.get('ppm_mirrors', []) if isinstance(cfg, dict) else []
        if not mirrors:
            # default primary
            mirrors = ["http://pryzma.dzordz.pl/api"]
        return mirrors

    def choose_mirrors_by_latency(mirrors, package_name, timeout=3):
        timings = []
        for m in mirrors:
            base = m.rstrip('/')
            url = f"{base}/download/{package_name}"
            try:
                import time
                t0 = time.time()
                r = requests.head(url, timeout=timeout, allow_redirects=True)
                if r.status_code == 200:
                    timings.append((time.time() - t0, m))
            except Exception:
                continue

        timings.sort(key=lambda x: x[0])
        return [m for _, m in timings]

    mirrors = get_ppm_mirrors()
    print(f"[ppm] Using {len(mirrors)} mirror(s)")

    # Probe mirrors to find reachable ones ordered by latency
    ordered_mirrors = choose_mirrors_by_latency(mirrors, package_name)

    tried_any = False
    for mirror in ordered_mirrors:
        tried_any = True
        primary_url = mirror.rstrip('/') + f"/download/{package_name}"
        print(f"Trying to download {package_name} from {primary_url}...")
        try:
            response = requests.get(primary_url, timeout=10)
            response.raise_for_status()

            print("Download succeeded. Extracting package...")
            with zipfile.ZipFile(io.BytesIO(response.content)) as zip_ref:
                zip_ref.extractall(package_path)
            print(f"{package_name} installed successfully from {mirror}.")
            return
        except Exception as e:
            print(f"Mirror {mirror} failed: {e}")

    # If we probed mirrors but none returned 200 on HEAD, fall back to trying mirrors in provided order
    if not tried_any and mirrors:
        for mirror in mirrors:
            primary_url = mirror.rstrip('/') + f"/download/{package_name}"
            print(f"Trying to download {package_name} from {primary_url} (fallback order)...")
            try:
                response = requests.get(primary_url, timeout=10)
                response.raise_for_status()

                print("Download succeeded. Extracting package...")
                with zipfile.ZipFile(io.BytesIO(response.content)) as zip_ref:
                    zip_ref.extractall(package_path)
                print(f"{package_name} installed successfully from {mirror}.")
                return
            except Exception as e:
                print(f"Mirror {mirror} failed: {e}")

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
        print("Package installation failed from all sources.")
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


### Local config helpers ###
def load_local_config():
    # Prefer local config; if it doesn't exist, fall back to global config
    local_path = CONFIG_PATHS[0]
    global_path = CONFIG_PATHS[1] if len(CONFIG_PATHS) > 1 else None

    # Try local first
    if os.path.exists(local_path):
        try:
            with open(local_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}

    # Fallback to global if present
    if global_path and os.path.exists(global_path):
        try:
            with open(global_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}

    return {}

def save_used_config(cfg):
    """Save cfg to the config file that would be used by load_local_config():
    prefer local CONFIG_PATHS[0] if it exists, otherwise use global CONFIG_PATHS[1].
    Creates parent dirs and writes atomically.
    """
    # determine the active config path (first existing or local default)
    target = get_active_config_path()

    os.makedirs(os.path.dirname(target), exist_ok=True)
    import tempfile
    try:
        with tempfile.NamedTemporaryFile('w', delete=False, dir=os.path.dirname(target), encoding='utf-8') as tf:
            json.dump(cfg, tf, indent=4)
            tmpname = tf.name
        os.replace(tmpname, target)
        return True
    except Exception as e:
        print(f"[config] Failed to write config to {target}: {e}")
        try:
            if 'tmpname' in locals() and os.path.exists(tmpname):
                os.remove(tmpname)
        except Exception:
            pass
        return False


def get_active_config_path():
    """Return the config path that load_config() would use (first existing in CONFIG_PATHS),
    or the local path (CONFIG_PATHS[0]) if none exist.
    """
    for path in CONFIG_PATHS:
        if os.path.exists(path):
            return path
    return CONFIG_PATHS[0]


def load_global_config():
    """Load only the global config file (CONFIG_PATHS[1]) and return a dict."""
    if len(CONFIG_PATHS) < 2:
        return {}
    cfg_path = CONFIG_PATHS[1]
    if not os.path.exists(cfg_path):
        return {}
    try:
        with open(cfg_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg, use_global=False):
    """Save cfg to local (default) or global config depending on use_global flag. Atomic write."""
    if use_global and len(CONFIG_PATHS) > 1:
        target = CONFIG_PATHS[1]
    else:
        target = CONFIG_PATHS[0]

    os.makedirs(os.path.dirname(target), exist_ok=True)
    import tempfile
    try:
        with tempfile.NamedTemporaryFile('w', delete=False, dir=os.path.dirname(target), encoding='utf-8') as tf:
            json.dump(cfg, tf, indent=4)
            tmpname = tf.name
        os.replace(tmpname, target)
        return True
    except Exception as e:
        print(f"[config] Failed to write config to {target}: {e}")
        try:
            if 'tmpname' in locals() and os.path.exists(tmpname):
                os.remove(tmpname)
        except Exception:
            pass
        return False

def ppm_mirrors_list(use_global=False):
    cfg = load_config() if not use_global else (load_global_config() if 'load_global_config' in globals() else {})
    mirrors = cfg.get('ppm_mirrors', [])
    if not mirrors:
        print("[mirrors] No mirrors configured. Default will be used.")
        return
    print("Configured mirrors:")
    for i, m in enumerate(mirrors, start=1):
        print(f" {i}. {m}")


def ppm_mirrors_add(url, use_global=False):
    cfg = load_config() if not use_global else (load_global_config() if 'load_global_config' in globals() else {})
    mirrors = cfg.get('ppm_mirrors', [])
    if url in mirrors:
        print("[mirrors] Mirror already exists in list")
        return False
    mirrors.append(url)
    cfg['ppm_mirrors'] = mirrors
    if use_global:
        ok = save_config(cfg, use_global=True)
    else:
        ok = save_used_config(cfg)
    if ok:
        print(f"[mirrors] Added mirror: {url}")
        return True
    return False


def ppm_mirrors_remove(identifier, use_global=False):
    cfg = load_config() if not use_global else (load_global_config() if 'load_global_config' in globals() else {})
    mirrors = cfg.get('ppm_mirrors', [])
    if not mirrors:
        print("[mirrors] No mirrors configured")
        return False

    # try treating identifier as index
    try:
        idx = int(identifier)
        if 1 <= idx <= len(mirrors):
            removed = mirrors.pop(idx-1)
            cfg['ppm_mirrors'] = mirrors
            if use_global:
                save_config(cfg, use_global=True)
            else:
                save_used_config(cfg)
            print(f"[mirrors] Removed mirror: {removed}")
            return True
    except Exception:
        pass

    # try treating identifier as exact url
    if identifier in mirrors:
        mirrors.remove(identifier)
        cfg['ppm_mirrors'] = mirrors
        if use_global:
            save_config(cfg, use_global=True)
        else:
            save_used_config(cfg)
        print(f"[mirrors] Removed mirror: {identifier}")
        return True

    print("[mirrors] Mirror not found")
    return False


def ppm_mirrors_test(timeout=3, use_global=False):
    cfg = load_config() if not use_global else (load_global_config() if 'load_global_config' in globals() else {})
    mirrors = cfg.get('ppm_mirrors', [])
    if not mirrors:
        mirrors = ["http://pryzma.dzordz.pl/api"]

    import time
    results = []
    for m in mirrors:
        try:
            t0 = time.time()
            r = requests.head(m, timeout=timeout, allow_redirects=True)
            elapsed = time.time() - t0
            status = r.status_code
            results.append((m, elapsed, status))
        except Exception as e:
            results.append((m, None, str(e)))

    print("Mirror test results:")
    for m, elapsed, status in results:
        if elapsed is None:
            print(f" - {m}: ERROR ({status})")
        else:
            print(f" - {m}: {elapsed:.3f}s (HTTP {status})")


def notes_list(proj_name):
    proj_path = os.path.join(PROJECTS_PATH, proj_name)
    if not os.path.exists(proj_path):
        print(f"[notes] Project '{proj_name}' doesn't exist")
        return

    notes_file = os.path.join(PROJECTS_PATH, proj_name, "notes")
    if not os.path.exists(notes_file):
        print(f"[notes] Notes file for project '{proj_name}' doesn't exist")
        return

    with open(notes_file) as f:
        notes = f.read().splitlines()

    notes = list(filter(None, map(str.strip, notes)))

    if len(notes) < 1:
        print(f"[notes] No notes found for project '{proj_name}'.")
        return

    print(f"Notes for project '{proj_name}':")

    for i, note in enumerate(notes):
        print(f"[{i+1}] {note}")

def notes_remove(proj_name, line):
    proj_path = os.path.join(PROJECTS_PATH, proj_name)
    if not os.path.exists(proj_path):
        print(f"[notes] Project '{proj_name}' doesn't exist")
        return
    notes_file = os.path.join(PROJECTS_PATH, proj_name, "notes")
    if not os.path.exists(notes_file):
        print(f"[notes] Notes file for project '{proj_name}' doesn't exist")
        return

    with open(notes_file) as f:
        all_lines = f.read().splitlines()

    non_empty_lines = [(i, ln) for i, ln in enumerate(all_lines) if ln.strip()]

    try:
        line_num = int(line)
        if line_num < 1 or line_num > len(non_empty_lines):
            print(f"[notes] Invalid line number {line_num} (valid range: 1-{len(non_empty_lines)})")
            return

        original_index, note_to_remove = non_empty_lines[line_num-1]

        all_lines.pop(original_index)

        with open(notes_file, "w") as f:
            f.write("\n".join(all_lines))

        print(f"[notes] Removed note: {note_to_remove}")

    except ValueError:
        print(f"[notes] Line number must be an integer, got '{line}'")

def ppm_fetch_and_print_packages(url = "http://pryzma.dzordz.pl/api/fetch"):
    import_err = False
    try:
        import requests
    except ImportError:
        import_err = True
        print("module requests not found")
    if not import_err:
        try:
            response = requests.get(url)
            if response.status_code == 200:
                package_list = response.json()
                if package_list:
                    print("Available packages:")
                    for package in package_list:
                        print("-", package)
                else:
                    print("No packages available on the server.")
            else:
                print("Failed to fetch packages from the server. Status code:", response.status_code)
        except requests.exceptions.RequestException as e:
            print("Error fetching packages:", e)

def notes_add(proj_name, note):
    proj_path = os.path.join(PROJECTS_PATH, proj_name)
    if not os.path.exists(proj_path):
        print(f"[notes] Project '{proj_name}' doesn't exist")
        return
    notes_file = os.path.join(PROJECTS_PATH, proj_name, "notes")
    if not os.path.exists(notes_file):
        print(f"[notes] Notes file for project '{proj_name}' doesn't exist")
        return

    with open(notes_file) as f:
        all_lines = f.read().splitlines()

    all_lines.append(note)

    with open(notes_file, "w") as f:
        f.write("\n".join(all_lines))

    print(f"[notes] Added note '{note}' to project '{proj_name}'")


def build_parser():
    parser = argparse.ArgumentParser(prog="pryzma-manager", description="Manage Pryzma projects and environments and more")
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

    proj_test = proj_subparsers.add_parser("test", help="Run tests for a specified project")
    proj_test.add_argument("proj_name", help="Name of the project to test")

    proj_build = proj_subparsers.add_parser("build", help="Build a specified project")
    proj_build.add_argument("proj_name", help="Name of the project to build")
    proj_build.add_argument("-a", "--auto-fetch", action="store_true", dest="auto_fetch", help="Automatically fetch missing Pryzma package dependencies via ppm when building")

    # Top-level build command (can build a project or a single file)
    build_cmd = subparsers.add_parser("build", help="Build a Pryzma project or file")
    build_cmd.add_argument("proj_name", nargs="?", help="Name of the project to build")
    build_cmd.add_argument("-f", "--file", dest="file", help="Build a single .pryzma file instead of a project")
    build_cmd.add_argument("-a", "--auto-fetch", action="store_true", dest="auto_fetch", help="Automatically fetch missing Pryzma package dependencies via ppm when building")

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
    ppm = subparsers.add_parser("ppm", help="Pryzma package manager")
    ppm.add_argument("action", choices=["install", "list", "remove", "info", "update", "fetch"])
    ppm.add_argument("package", nargs="?")

    # Mirrors management for ppm
    mirrors_parser = subparsers.add_parser("mirrors", help="Manage ppm mirrors")
    mirrors_sub = mirrors_parser.add_subparsers(dest="mirrors_action")

    mirrors_add = mirrors_sub.add_parser("add", help="Add a mirror (base URL)")
    mirrors_add.add_argument("url", help="Mirror base URL (e.g. https://mirror.example/api)")
    mirrors_add.add_argument("--global", action="store_true", dest="use_global", help="Write mirror to global config (~/.pryzma/config.json) instead of local config")

    mirrors_list = mirrors_sub.add_parser("list", help="List configured mirrors")
    mirrors_list.add_argument("--global", action="store_true", dest="use_global", help="Read mirrors from global config instead of local")

    mirrors_remove = mirrors_sub.add_parser("remove", help="Remove a mirror by index or URL")
    mirrors_remove.add_argument("id", help="Mirror index (1-based) or exact URL to remove")
    mirrors_remove.add_argument("--global", action="store_true", dest="use_global", help="Remove mirror from global config instead of local")

    mirrors_test = mirrors_sub.add_parser("test", help="Test mirrors for latency and reachability")
    mirrors_test.add_argument("--global", action="store_true", dest="use_global", help="Test mirrors defined in global config instead of local")

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

    plugin_parser = subparsers.add_parser("plugin", help="Manage plugins")
    plugin_subparsers = plugin_parser.add_subparsers(dest="plugin_command")

    list_parser = plugin_subparsers.add_parser("list", help="List plugins")
    list_parser.add_argument("-v", "--verbose", action="store_true", help="Show detailed plugin info")

    toggle_parser = plugin_subparsers.add_parser("toggle", help="Enable/disable plugin")
    toggle_parser.add_argument("name", help="Plugin name")
    toggle_parser.add_argument("--enable", action="store_true", help="Enable plugin")
    toggle_parser.add_argument("--disable", action="store_true", help="Disable plugin")

    info_parser = plugin_subparsers.add_parser("info", help="Show plugin details")
    info_parser.add_argument("name", help="Plugin name")

    # Notes command
    notes_parser = subparsers.add_parser("notes", help="Manage notes")
    notes_subparsers = notes_parser.add_subparsers(dest="notes_action")

    list_parser = notes_subparsers.add_parser("list", help="List all notes for a given project")
    list_parser.add_argument("project_name", help="Name of the project")

    notes_remove_parser = notes_subparsers.add_parser("remove", help="Remove notes from a given project")
    notes_remove_parser.add_argument("project_name", help="Name of the project")
    notes_remove_parser.add_argument("line", help="Line number")

    notes_add_parser = notes_subparsers.add_parser("add", help="Adds a note to a given project")
    notes_add_parser.add_argument("project_name", help="Name of the project")
    notes_add_parser.add_argument("note", help="note content")

    return parser

def main():
    init_main_env()
    parser = build_parser()

    load_plugins(parser)

    args = parser.parse_args()

    if hasattr(args, 'func'):
        args.func(args)
        return

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
        elif args.proj_command == "test":
            test_project(args)
        elif args.proj_command == "build":
            build_project(args)
        else:
            print("[proj] Unknown project subcommand.")
    elif args.command == "run":
        run_script(args.path, args.debug)
    elif args.command == "build":
        if getattr(args, 'file', None):
            build_file(args.file, getattr(args, 'auto_fetch', False))
        elif getattr(args, 'proj_name', None):
            build_project(args)
        else:
            print("[build] Please specify a project name or use -f/--file to build a single file.")
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
        elif args.action == "fetch":
            ppm_fetch_and_print_packages()
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
    elif args.command == "plugin":
        if args.plugin_command == "list":
            plugins = list_plugins()
            if args.verbose:
                print("\nDetailed info:")
                for plugin in plugins:
                    show_plugin_info(plugin["name"])
                    print()
            return
        elif args.plugin_command == "toggle":
            if args.enable:
                toggle_plugin(args.name, enable=True)
            elif args.disable:
                toggle_plugin(args.name, enable=False)
            else:
                plugins = list_plugins(show_all=True)
                for p in plugins:
                    if p["name"] == args.name:
                        toggle_plugin(args.name, enable=p["disabled"])
                        return
                print(f"Plugin not found: {args.name}")
            return
        elif args.plugin_command == "info":
            show_plugin_info(args.name)
            return
    elif args.command == "notes":
        if args.notes_action == "list":
            notes_list(args.project_name)
        elif args.notes_action == "remove":
            notes_remove(args.project_name, args.line)
        elif args.notes_action == "add":
            notes_add(args.project_name, args.note)
        else:
            print("[notes] Unknown notes subcommand.")
    elif args.command == "mirrors":
        if args.mirrors_action == "list":
            ppm_mirrors_list()
        elif args.mirrors_action == "add":
            ppm_mirrors_add(args.url)
        elif args.mirrors_action == "remove":
            ppm_mirrors_remove(args.id)
        elif args.mirrors_action == "test":
            ppm_mirrors_test()
        else:
            print("[mirrors] Unknown mirrors subcommand.")
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

