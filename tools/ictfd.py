import os
import sys
import time
import argparse
import configparser
import requests
from urllib.parse import urlparse
from datetime import datetime

VERSION = "2.0"
GITHUB_API_URL = "https://api.github.com/repos/IgorCielniak/ictfd/releases/latest"
GITHUB_RELEASE_URL = f"https://raw.githubusercontent.com/IgorCielniak/ictfd/main/ictfd.py"

DEFAULT_CONFIG = {
    "chunk_size": 8192,
    "timeout": 5,
    "retries": 3,
    "download_dir": os.path.join(os.path.expanduser("~"), "Downloads")
}

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".ictfd")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.ini")


def load_config():
    config = configparser.ConfigParser()
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w") as f:
            f.write(
                "[defaults]\n"
                "chunk_size = 8192\n"
                "timeout = 5\n"
                "retries = 3\n"
                "download_dir = ~/Downloads\n"
            )
    config.read(CONFIG_FILE)
    return config


def format_bytes(size):
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0


def format_time(seconds):
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}"


def create_folder(path):
    if not os.path.exists(path):
        os.makedirs(path)


def download_http_file(url, dest_path, chunk_size, timeout, retries):
    file_name = os.path.join(dest_path, os.path.basename(url))
    for attempt in range(retries):
        try:
            if os.path.exists(file_name):
                choice = input(f"'{file_name}' exists. Overwrite? (y/n): ").lower()
                if choice != "y":
                    print("Download canceled.")
                    return

            response = requests.get(url, stream=True, timeout=timeout)
            response.raise_for_status()

            total_size = int(response.headers.get("content-length", 0))
            parsed_url = urlparse(url)

            print(f"{url}")
            print(f"Resolving {parsed_url.netloc}... connected.")
            print(f"HTTP request sent, awaiting response... {response.status_code} {response.reason}")
            print(f"Length: {total_size} ({format_bytes(total_size)}) [{response.headers['content-type']}]")
            print(f"Saving to: '{file_name}'")
            print(f"Using chunk size: {chunk_size} bytes")
            print("Press Ctrl+C to cancel the download.")

            start_time = datetime.now()
            downloaded = 0

            with open(file_name, "wb") as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

                        elapsed = (datetime.now() - start_time).total_seconds()
                        speed = downloaded / elapsed if elapsed > 0 else 0

                        if total_size > 0:
                            percent = (downloaded / total_size) * 100
                            percent = min(percent, 100)
                            remaining = (total_size - downloaded) / speed if speed > 0 else 0
                            print(
                                f"\rSpeed: {format_bytes(speed)}/s | "
                                f"Progress: {percent:.2f}% | "
                                f"ETA: {remaining:.0f}s", end="", flush=True
                            )
                        else:
                            print(
                                f"\rSpeed: {format_bytes(speed)}/s | "
                                f"Downloaded: {format_bytes(downloaded)}", end="", flush=True
                            )
            break
        except requests.RequestException as e:
            print(f"\nError: {e}")
            if attempt < retries - 1:
                print("Retrying in 5 seconds...")
                time.sleep(5)
            else:
                print("Max retries reached. Download failed.")
                return
        except KeyboardInterrupt:
            print("\nDownload interrupted. Cleaning up...")
            if os.path.exists(file_name):
                os.remove(file_name)
            print("Partial file deleted.")
            return

    print("\nDownload complete.")
    print(f"Elapsed time: {format_time((datetime.now() - start_time).total_seconds())}")


def check_for_updates():
    try:
        latest_version = requests.get(GITHUB_API_URL).json()["tag_name"]
        if latest_version != VERSION:
            print(f"\nA newer version ({latest_version}) is available.")
            print(f"Download: {GITHUB_RELEASE_URL}")
            if input("Download now? (y/n): ").lower() == "y":
                download_http_file(GITHUB_RELEASE_URL, os.path.dirname(os.path.abspath(__file__)),
                                   DEFAULT_CONFIG["chunk_size"], DEFAULT_CONFIG["timeout"], DEFAULT_CONFIG["retries"])
        else:
            print("You are using the latest version.")
    except Exception as e:
        print("Update check failed:", e)


def main():
    config = load_config()

    parser = argparse.ArgumentParser(description="ICTFD - CLI file downloader")
    parser.add_argument("url", nargs="?", help="The URL of the file to download.")
    parser.add_argument("-c", "--chunk-size", type=int, default=int(config["defaults"].get("chunk_size", DEFAULT_CONFIG["chunk_size"])))
    parser.add_argument("-d", "--download-dir", default=os.path.expanduser(config["defaults"].get("download_dir", DEFAULT_CONFIG["download_dir"])))
    parser.add_argument("-t", "--timeout", type=int, default=int(config["defaults"].get("timeout", DEFAULT_CONFIG["timeout"])))
    parser.add_argument("-r", "--retries", type=int, default=int(config["defaults"].get("retries", DEFAULT_CONFIG["retries"])))
    parser.add_argument("-v", "--version", action="store_true", help="Show version info and check for updates.")
    
    args = parser.parse_args()

    if args.version:
        print(f"ICTFD Version {VERSION}")
        check_for_updates()
        sys.exit()

    if not args.url:
        parser.print_help()
        sys.exit()

    parsed_url = urlparse(args.url)
    if parsed_url.scheme not in ["http", "https"]:
        print(f"Unsupported scheme: {parsed_url.scheme}")
        sys.exit()

    create_folder(args.download_dir)
    download_http_file(args.url, args.download_dir, args.chunk_size, args.timeout, args.retries)


if __name__ == "__main__":
    main()

