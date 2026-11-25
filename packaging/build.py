"""Gera um executável com runtime Python, certificados e avisos de terceiros."""
import argparse
import importlib.metadata
import platform
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--name", required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parent.parent
licenses = root / "build" / "licenses"
licenses.mkdir(parents=True, exist_ok=True)
shutil.copy(root / "LICENSE", licenses / "ABYSS-LICENSE.txt")
for package in ("pyinstaller", "certifi"):
    dist = importlib.metadata.distribution(package)
    for file in dist.files or []:
        if file.name.lower().startswith(("license", "copying")):
            shutil.copyfile(dist.locate_file(file), licenses / (package + "-" + file.name))
python_license = Path(sys.base_prefix) / "LICENSE.txt"
if python_license.is_file():
    shutil.copy(python_license, licenses / "Python-LICENSE.txt")
else:
    url = f"https://raw.githubusercontent.com/python/cpython/v{platform.python_version()}/LICENSE"
    with urllib.request.urlopen(url, timeout=20) as response:
        (licenses / "Python-LICENSE.txt").write_bytes(response.read())
(licenses / "NOTICES.txt").write_text("ABYSS includes Python (PSF license) and certifi certificates (MPL-2.0). Built with PyInstaller (GPL with bootloader exception). Third-party rights are governed by their respective licenses.\n", encoding="utf-8")
subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--console", "--name", args.name,
                "--add-data", str(licenses) + ":licenses", str(root / "abyss.py")], cwd=root, check=True)
