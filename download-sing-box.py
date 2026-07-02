#!/usr/bin/env python3
import os
import sys
import urllib.request
import zipfile
import shutil

VERSION = "1.13.14"
URL = f"https://github.com/SagerNet/sing-box/releases/download/v{VERSION}/sing-box-{VERSION}-windows-amd64.zip"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ZIP_FILE = os.path.join(SCRIPT_DIR, "_singbox.zip")
TEMP_DIR = os.path.join(SCRIPT_DIR, "_singbox_temp")

def main():
    print("=" * 40)
    print("  sing-box Auto Downloader")
    print("=" * 40)
    print()

    # Download
    print(f"[1/4] Downloading sing-box v{VERSION} ...")
    print(f"URL: {URL}")
    try:
        urllib.request.urlretrieve(URL, ZIP_FILE)
        print("Download OK")
    except Exception as e:
        print(f"Download FAILED: {e}")
        input("Press Enter to exit")
        return

    # Extract
    print()
    print("[2/4] Extracting ...")
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)
    with zipfile.ZipFile(ZIP_FILE, 'r') as z:
        z.extractall(TEMP_DIR)
    print("Extract OK")

    # Find and copy sing-box.exe
    print()
    print("[3/4] Copying sing-box.exe ...")
    found = False
    for root, dirs, files in os.walk(TEMP_DIR):
        if "sing-box.exe" in files:
            src = os.path.join(root, "sing-box.exe")
            dst = os.path.join(SCRIPT_DIR, "sing-box.exe")
            shutil.copy2(src, dst)
            print(f"Copied to: {dst}")
            found = True
            break

    if not found:
        print("ERROR: sing-box.exe not found")

    # Cleanup
    print()
    print("[4/4] Cleaning up ...")
    if os.path.exists(ZIP_FILE):
        os.remove(ZIP_FILE)
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)

    print()
    print("=" * 40)
    if found:
        print("Done! sing-box.exe is ready")
    else:
        print("Failed to get sing-box.exe")
    print("=" * 40)
    print()
    input("Press Enter to exit")

if __name__ == "__main__":
    main()
