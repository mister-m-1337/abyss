"""Preferências sem credenciais; chave Brave é solicitada apenas para a sessão."""
import getpass
import json
import os
from pathlib import Path
from urllib.parse import urlsplit


def config_root():
    from abyss_installer import default_root, installed_root
    if os.environ.get("ABYSS_CONFIG_DIR"):
        return Path(os.environ["ABYSS_CONFIG_DIR"])
    return installed_root() or default_root()


def read_config(root=None):
    try:
        data = json.loads((Path(root or config_root()) / "config.json").read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def load_environment():
    config = read_config()
    if config.get("searxng_url"):
        os.environ.setdefault("SEARXNG_URL", config["searxng_url"])
    return config


def configure(root=None):
    from abyss_installer import atomic_write
    root = Path(root or config_root())
    print("\nCONFIGURAÇÃO — [1] Brave API  [2] SearXNG existente  [3] Manual")
    selection = input("Escolha [3]: ").strip() or "3"
    if selection not in {"1", "2", "3"}:
        raise ValueError("Opção inválida")
    settings = {"provider": {"1": "brave", "2": "searxng", "3": "manual"}[selection]}
    if selection == "1":
        print("Use sua própria chave Brave. Ela ficará somente na memória desta sessão.")
        key = getpass.getpass("Chave Brave (vazio para configurar depois): ").strip()
        if key:
            os.environ["BRAVE_API_KEY"] = key
    elif selection == "2":
        address = input("URL da instância SearXNG com JSON habilitado: ").strip().rstrip("/")
        parsed = urlsplit(address)
        if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or (parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"})):
            raise ValueError("Use HTTPS sem credenciais/parâmetros, ou HTTP local")
        settings["searxng_url"] = address
        os.environ["SEARXNG_URL"] = address
    root.mkdir(parents=True, exist_ok=True)
    atomic_write(root / "config.json", json.dumps(settings, ensure_ascii=False, indent=2))
    print("Preferência salva. Nenhuma chave foi gravada em arquivo.")
    return settings
