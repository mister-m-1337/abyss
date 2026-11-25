"""Atualizações por releases estáveis do repositório oficial, sem executar scripts remotos."""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from abyss_network import tls_context

REPOSITORY = "mister-m-1337/abyss"
API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r"v?\d+\.\d+\.\d+", value):
        raise ValueError("Release deve usar versão estável vMAJOR.MINOR.PATCH")
    return tuple(int(x) for x in value.lstrip("v").split("."))


def cache_path():
    base = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
    return base / "abyss" / "release.json"


def check_update(current, force=False, cache=None):
    cache = Path(cache) if cache else cache_path()
    release = None
    fetched = False
    if not force:
        try:
            stored = json.loads(cache.read_text())
            if 0 <= time.time() - stored["checked_at"] < 86400:
                release = stored["release"]
        except (OSError, ValueError, KeyError, TypeError):
            pass
    if release is None:
        req = Request(API, headers={"Accept": "application/vnd.github+json", "User-Agent": "ABYSS-Update-Checker"})
        with urlopen(req, timeout=3, context=tls_context()) as response:
            raw = response.read(1_000_001)
        if len(raw) > 1_000_000:
            raise ValueError("Resposta de release excede o limite permitido")
        release = json.loads(raw)
        fetched = True
    if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
        raise ValueError("Resposta de release inválida")
    tag = release.get("tag_name")
    latest = version_tuple(tag)
    result = {"current": current, "latest": tag, "update_available": latest > version_tuple(current),
              "url": f"https://github.com/{REPOSITORY}/releases/tag/{tag}",
              "name": str(release.get("name") or tag), "published_at": release.get("published_at", "")}
    try:
        if not fetched:
            return result
        cache.parent.mkdir(parents=True, exist_ok=True)
        # Não guarda tokens, notas remotas nem dados de pesquisa.
        payload = {"checked_at": time.time(), "release": {k: release.get(k) for k in ("tag_name", "name", "published_at", "draft", "prerelease")}}
        temporary = cache.with_name(cache.name + f".{os.getpid()}.tmp")
        temporary.write_text(json.dumps(payload), encoding="utf-8")
        temporary.replace(cache)
    except OSError:
        pass
    return result


def git(repo, *args, timeout=60):
    try:
        result = subprocess.run(["git", "-C", str(repo), *args], text=True, capture_output=True, timeout=timeout,
                                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    except subprocess.TimeoutExpired as exc:
        raise ValueError("Git excedeu o tempo limite. Nenhuma limpeza forçada foi executada; confira o estado local.") from exc
    if result.returncode:
        raise ValueError("Git não concluiu a operação. Confira instalação, rede e histórico local.")
    return result.stdout.strip()


def apply_update(current, repo=None):
    if getattr(sys, "frozen", False) and repo is None:
        from abyss_installer import update_binary
        return update_binary(current)
    repo = Path(repo) if repo else Path(__file__).resolve().parent
    latest = check_update(current, force=True)
    if not latest["update_available"]:
        return {**latest, "updated": False}
    # Impede operar em um repositório pai se o ZIP foi extraído dentro de outro projeto.
    if Path(git(repo, "rev-parse", "--show-toplevel")).resolve() != repo.resolve():
        raise ValueError("Instale o ABYSS via git clone para usar o atualizador")
    remote = git(repo, "remote", "get-url", "origin").rstrip("/")
    allowed = {f"https://github.com/{REPOSITORY}", f"https://github.com/{REPOSITORY}.git", f"git@github.com:{REPOSITORY}.git", f"ssh://git@github.com/{REPOSITORY}.git"}
    if remote not in allowed:
        raise ValueError("origin não corresponde ao repositório oficial do ABYSS")
    if git(repo, "status", "--porcelain"):
        raise ValueError("Atualização bloqueada: há alterações ou arquivos locais não versionados. Preserve-os antes de atualizar.")
    if git(repo, "branch", "--show-current") != "main":
        raise ValueError("Atualização requer a branch main; nenhuma troca automática será feita")
    tag = latest["latest"]  # validada como semver; nunca conteúdo executável.
    git(repo, "fetch", "--no-tags", "origin", f"refs/tags/{tag}:refs/tags/{tag}")
    git(repo, "merge-base", "--is-ancestor", "HEAD", f"refs/tags/{tag}")
    # Revalida depois do acesso à rede, sem reset, checkout forçado ou clean.
    if git(repo, "status", "--porcelain"):
        raise ValueError("Arquivos locais mudaram durante a verificação; atualização cancelada")
    git(repo, "merge", "--ff-only", f"refs/tags/{tag}")
    return {**latest, "updated": True, "restart_required": True}
