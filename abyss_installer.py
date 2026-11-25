"""Instalação por usuário e atualização dos executáveis oficiais do ABYSS."""
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import sys
import tempfile
from pathlib import Path
from urllib.request import Request, urlopen

from abyss_network import tls_context

REPO = "mister-m-1337/abyss"


def default_root():
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "ABYSS"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/ABYSS"
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / "abyss"


def platform_asset(system=None, machine=None):
    system = system or platform.system()
    machine = (machine or platform.machine()).lower()
    arch = {"amd64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(machine)
    os_name = {"Windows": "windows", "Darwin": "macos", "Linux": "linux"}.get(system)
    if (os_name, arch) not in {("windows", "x64"), ("macos", "arm64"), ("macos", "x64"), ("linux", "x64")}:
        raise ValueError("Ainda não há instalador oficial para este sistema/arquitetura")
    return f"ABYSS-Setup-{os_name}-{arch}" + (".exe" if os_name == "windows" else "")


def installed_root(executable=None):
    executable = Path(executable or sys.executable).resolve()
    if executable.parent.parent.name == "versions":
        root = executable.parent.parent.parent
        if (root / "installation.json").is_file():
            return root
    return None


def atomic_write(path, data):
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    temporary.write_text(data, encoding="utf-8")
    temporary.replace(path)


def write_launchers(root, executable, desktop=False):
    if sys.platform == "win32":
        launcher = root / "ABYSS.cmd"
        relative = str(executable.relative_to(root)).replace("/", "\\")
        text = f'@echo off\ncd /d "%~dp0"\n"%~dp0{relative}" --ui\npause\n'
    else:
        launcher = root / ("ABYSS.command" if sys.platform == "darwin" else "ABYSS.sh")
        text = f"#!/bin/sh\ncd {shlex.quote(str(root))} || exit 1\nexec {shlex.quote(str(executable))} --ui\n"
    atomic_write(launcher, text)
    launcher.chmod(0o700)
    shortcut = None
    desktop_folder = Path.home() / "Desktop"
    if desktop and desktop_folder.is_dir():
        shortcut = desktop_folder / launcher.name
        # Não sobrescreve atalhos do usuário: nome alternativo exclusivo.
        if shortcut.exists():
            shortcut = desktop_folder / ("ABYSS-" + executable.parent.name + launcher.suffix)
        counter = 1
        while shortcut.exists():
            shortcut = desktop_folder / f"ABYSS-{counter}{launcher.suffix}"
            counter += 1
        shortcut_text = ('@echo off\ncall "' + str(launcher).replace('%', '%%') + '"\n') if sys.platform == "win32" else text
        with shortcut.open("x", encoding="utf-8") as f:
            f.write(shortcut_text)
        shortcut.chmod(0o700)
    return launcher, shortcut


def install_binary(source, version, destination=None, desktop=False):
    from abyss_updates import version_tuple
    version_tuple(version)
    root = Path(destination or default_root()).expanduser().resolve()
    source = Path(source).resolve()
    if not source.is_file():
        raise ValueError("Executável de instalação não encontrado")
    tag = "v" + version.lstrip("v")
    target = root / "versions" / tag / ("ABYSS.exe" if sys.platform == "win32" else "ABYSS")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise ValueError("Já existe um executável diferente para esta versão; nenhum arquivo foi substituído")
    else:
        temporary = target.with_name(target.name + ".installing")
        with source.open("rb") as incoming, temporary.open("xb") as outgoing:
            shutil.copyfileobj(incoming, outgoing)
        temporary.chmod(0o700)
        temporary.replace(target)
    (root / "output").mkdir(exist_ok=True)
    launcher, shortcut = write_launchers(root, target, desktop)
    licenses = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "licenses"
    if licenses.is_dir():
        shutil.copytree(licenses, target.parent / "licenses", dirs_exist_ok=True)
    atomic_write(root / "installation.json", json.dumps({"version": tag, "executable": str(target.relative_to(root)),
                 "sha256": digest, "launcher": launcher.name}, ensure_ascii=False, indent=2))
    return {"installed": True, "version": tag, "root": str(root), "executable": str(target),
            "launcher": str(launcher), "shortcut": str(shortcut) if shortcut else None}


def download(url, target, limit):
    if not url.startswith(f"https://github.com/{REPO}/releases/download/"):
        raise ValueError("Download fora do repositório oficial")
    req = Request(url, headers={"User-Agent": "ABYSS-Installer"})
    with urlopen(req, timeout=30, context=tls_context()) as response, target.open("xb") as output:
        size = 0
        while True:
            block = response.read(1024 * 1024)
            if not block:
                break
            size += len(block)
            if size > limit:
                raise ValueError("Download excede o tamanho permitido")
            output.write(block)


def update_binary(current, executable=None):
    from abyss_updates import check_update
    info = check_update(current, force=True)
    if not info["update_available"]:
        return {**info, "updated": False}
    root = installed_root(executable)
    if not root:
        raise ValueError("Execute primeiro o instalador para usar a atualização sem Git")
    name = platform_asset()
    base = f"https://github.com/{REPO}/releases/download/{info['latest']}/{name}"
    with tempfile.TemporaryDirectory(prefix="abyss-download-") as temp:
        checksum, binary = Path(temp) / "checksum", Path(temp) / name
        download(base + ".sha256", checksum, 1024)
        expected = checksum.read_text().split()[0]
        if not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError("Manifesto de integridade inválido")
        download(base, binary, 150 * 1024 * 1024)
        if hashlib.sha256(binary.read_bytes()).hexdigest() != expected:
            raise ValueError("Checksum divergente; atualização cancelada")
        result = install_binary(binary, info["latest"], root)
    return {**info, **result, "updated": True, "restart_required": True}


def setup(version, destination=None, guided=False, desktop=False, run=None):
    if not getattr(sys, "frozen", False):
        raise ValueError("Baixe o instalador executável da release; este comando não empacota o Python local")
    if guided:
        print("\nABYSS — Instalação por usuário (sem administrador)")
        print("Python e certificados já estão incluídos. Nenhuma ferramenta global será alterada.")
        destination = input(f"Pasta de instalação [{default_root()}]: ").strip() or str(default_root())
        desktop = input("Criar lançador na Área de Trabalho? s/N: ").strip().lower() == "s"
    result = install_binary(sys.executable, version, destination, desktop)
    print(f"Instalado em: {result['root']}\nLançador: {result['launcher']}")
    if guided:
        os.chdir(result["root"])
        if input("Configurar buscador agora? s/N: ").strip().lower() == "s":
            from abyss_config import configure
            configure(root=Path(result["root"]))
        return run(["--ui"]) if run else 0
    print(json.dumps(result, ensure_ascii=False))
    return 0
