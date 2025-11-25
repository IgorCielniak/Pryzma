import os
import sys
import json
import shutil
import subprocess
import requests
import zipfile
import io
from pathlib import Path

PACKAGES_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)), "..", "Pryzma-programming-language", "packages")

def install(package_name):
    os.makedirs(PACKAGES_DIR, exist_ok=True)
    package_path = os.path.join(PACKAGES_DIR, package_name)

    if os.path.exists(package_path):
        print(f"Package '{package_name}' is already installed.")
        return

    # === PRIMARY SOURCE ===
    primary_url = f"http://pryzma.dzord.pl/api/download/{package_name}"
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

def list_packages():
    if not os.path.isdir(PACKAGES_DIR):
        return []

    packages = os.listdir(PACKAGES_DIR)
    return packages

def remove(package_name):
    package_path = os.path.join(PACKAGES_DIR, package_name)

    if os.path.isdir(package_path):
        shutil.rmtree(package_path)
        return True
    else:
        return False

def info(package_name):
    metadata_path = os.path.join(PACKAGES_DIR, package_name, "metadata.json")

    if not os.path.isfile(metadata_path):
        return None

    try:
        with open(metadata_path, "r") as f:
            data = json.load(f)
        return data
    except Exception as e:
        print(f"Error reading metadata: {e}")
        return None

def update(package_name):
    print(f"Updating {package_name}...")
    package_path = os.path.join(PACKAGES_DIR, package_name)
    if os.path.exists(package_path):
        shutil.rmtree(package_path)
    install(package_name)
    print(f"Updated {package_name} successfully.\n")

def update_all():
    if not Path(PACKAGES_DIR).exists():
        print("No packages installed.")
        return
    
    for pkg in Path(PACKAGES_DIR).iterdir():
        if pkg.is_dir():
            update(pkg.name)

def fetch_and_print_packages(url = "http://pryzma.dzordz.pl/api/fetch"):
    import_err = False
    try:
        import requests
    except ImportError:
        import_err = True
        return "module requests not found"
    if not import_err:
        try:
            response = requests.get(url)
            if response.status_code == 200:
                package_list = response.json()
                if package_list:
                    return package_list
                else:
                    return "No packages available on the server."
            else:
                return "Failed to fetch packages from the server. Status code:" + str(response.status_code)
        except requests.exceptions.RequestException as e:
            return "Error fetching packages: " + str(e)