"""Menu textual portátil: entrada padrão, saída padrão e nenhuma dependência."""
import contextlib
import getpass
import io
import json
import os
import shutil
import sys
import textwrap
from pathlib import Path

from abyss_exports import export_research, load_research, visible


def say(text=""):
    print(visible(text))


def ask(label, default=""):
    answer = input(f"{label}" + (f" [{default}]" if default else "") + ": ").strip()
    return answer or default


def number(label, default, low, high):
    while True:
        try:
            value = int(ask(label, str(default)))
            if low <= value <= high:
                return value
        except ValueError:
            pass
        say(f"Informe um número entre {low} e {high}.")


def display_sources(data, term="", page=0):
    width = min(120, max(50, shutil.get_terminal_size((90, 24)).columns))
    sources = [(i, s) for i, s in enumerate(data["sources"], 1)
               if term.casefold() in json.dumps(s, ensure_ascii=False).casefold()]
    total_pages = max(1, (len(sources) + 7) // 8)
    page = min(max(page, 0), total_pages - 1)
    say(f"\nRESULTADOS | {len(sources)} fontes | página {page + 1}/{total_pages}")
    say("─" * width)
    for index, source in sources[page * 8:(page + 1) * 8]:
        evidence = source["evidence"][0] if source["evidence"] else {}
        title = visible(evidence.get("title") or source["url"]).replace("\n", " ").replace("\t", " ")
        say(f"{index:>3}  {textwrap.shorten(title, width=width - 6, placeholder='…')}")
        say("     " + textwrap.shorten(visible(source["url"]), width=width - 6, placeholder="…"))
        categories = sorted({visible(e.get("category", "")) for e in source["evidence"]})
        say("     " + ", ".join(categories))
        signals = source.get("target_signals", {})
        if signals:
            label = "domínio oficial informado" if signals.get("official_domain") else ("nome encontrado no trecho" if signals.get("names_in_title_or_snippet") else "relação com alvo requer revisão")
            say("     Triagem: " + label)
    if not sources:
        say("Nenhuma fonte encontrada. Um plano manual não executa buscas na internet.")
    return page, total_pages


def show_detail(data, index):
    source = data["sources"][index - 1]
    say(f"\nFONTE {index} — {source.get('source_kind', '')}\n{source['url']}")
    for e in source["evidence"]:
        for label, key in [("Título", "title"), ("Categoria", "category"), ("Trecho", "snippet"),
                           ("Publicação informada", "published_date_reported"), ("Coleta UTC", "collected_at"),
                           ("Consulta", "query"), ("Provedor", "provider"), ("Evidência", "evidence_type"), ("Status", "status")]:
            say(f"{label}: {e.get(key) or 'não informado'}")
        for snippet in e.get("extra_snippets", []):
            say("Trecho adicional: " + snippet)
        say()


def browse(path):
    path, data = load_research(path)
    page, term = 0, ""
    say(f"\nALVO: {data['target'].get('company', '')} | {data['target'].get('location', '')}")
    say(f"Requisições registradas: {len(data['queries'])} | Consultas planejadas: {len(data['plan'])} | Falhas históricas: {sum(q.get('status') == 'error' for q in data['queries'])}")
    if data["target"].get("execution"):
        say("Encerramento: " + data["target"]["execution"].get("stop_reason", ""))
    while True:
        page, total = display_sources(data, term, page)
        say("[n] próxima  [p] anterior  [f] filtrar  [d] detalhes  [c] consultas")
        say("[1] PDF  [2] Excel (.xlsx)  [3] ambos  [0] voltar")
        choice = ask("Escolha").lower()
        if choice == "0":
            return
        if choice == "n":
            page = min(page + 1, total - 1)
        elif choice == "p":
            page = max(page - 1, 0)
        elif choice == "f":
            term, page = ask("Filtrar por palavra/categoria (vazio limpa)"), 0
        elif choice == "d" and data["sources"]:
            show_detail(data, number("Número da fonte", 1, 1, len(data["sources"])))
            ask("Enter para voltar")
        elif choice == "c":
            if not data["queries"]:
                say("Nenhuma consulta executada; o plano está em queries.txt.")
            for q in data["queries"]:
                say(f"[{q.get('status', '')}] {q.get('query', '')}")
                if q.get("error"):
                    say(q["error"])
            ask("Enter para voltar")
        elif choice in {"1", "2", "3"}:
            formats = {"1": ["pdf"], "2": ["xlsx"], "3": ["pdf", "xlsx"]}[choice]
            try:
                for file in export_research(path, formats):
                    say(f"Exportado: {file}")
            except (ValueError, OSError) as exc:
                say(f"Não foi possível exportar ({type(exc).__name__}); confira a pasta da pesquisa.")
            ask("Enter para voltar")


def new_search(run):
    say("\nNOVA PESQUISA — apenas consultas de leitura")
    company = ""
    while not company:
        company = ask("Empresa-alvo")
    args = ["--company", company]
    location = ask("Cidade/unidade (opcional)")
    if location:
        args += ["--location", location]
    for flag, label in [("--domain", "Domínios oficiais, separados por vírgula (opcional)"),
                        ("--alias", "Nomes alternativos, separados por vírgula (opcional)")]:
        args.extend(part for value in ask(label).split(",") if value.strip() for part in [flag, value.strip()])
    say("[1] Brave API  [2] SearXNG  [3] Plano manual/importação  [4] Ambos")
    from abyss_config import read_config
    preferred = {"brave": 1, "searxng": 2, "manual": 3}.get(read_config().get("provider"), 3)
    provider = {1: "brave", 2: "searxng", 3: "manual", 4: "both"}[number("Provedor", preferred, 1, 4)]
    args += ["--provider", provider]
    if provider in {"brave", "both"} and not os.environ.get("BRAVE_API_KEY"):
        key = getpass.getpass("Chave Brave (somente nesta sessão; vazio cancela): ").strip()
        if not key:
            say("Chave não informada; escolha outro provedor ou configure depois.")
            return
        os.environ["BRAVE_API_KEY"] = key
    if provider in {"searxng", "both"}:
        endpoint = ask("URL da instância SearXNG", os.environ.get("SEARXNG_URL", "http://localhost:8080"))
        args += ["--searxng-url", endpoint]
    if provider != "manual":
        args += ["--max-queries", str(number("Limite de consultas", 9, 1, 1000)),
                 "--count", str(number("Resultados por consulta", 10, 1, 20))]
        args += ["--pages", str(number("Páginas por consulta/provedor", 1, 1, 10)),
                 "--max-requests", str(number("Limite total de chamadas", 30, 1, 1000))]
        freshness = {1: "all", 2: "day", 3: "month", 4: "year"}[number("Período: 1=todos 2=dia 3=mês 4=ano", 1, 1, 4)]
        args += ["--freshness", freshness]
        say("A execução usa o provedor configurado e pode consumir sua cota.")
    if ask("Opções avançadas (nomes, temas e busca profunda)? s/N", "n").lower() == "s":
        args += ["--depth", "deep"]
        for flag, label in [("--person", "Profissionais conhecidos, separados por vírgula"), ("--keyword", "Temas específicos, separados por vírgula"), ("--exclude-domain", "Domínios a excluir, separados por vírgula")]:
            args.extend(part for value in ask(label).split(",") if value.strip() for part in [flag, value.strip()])
    imported = ask("Arquivo JSON de referências (opcional)")
    if imported:
        args += ["--import-json", str(Path(imported).expanduser())]
    say("Preparando pesquisa…" if provider == "manual" else "Buscando… acompanhe o progresso abaixo.")
    output = io.StringIO()
    try:
        with contextlib.redirect_stdout(output):
            code = run(args)
        result = json.loads(output.getvalue())
    except (SystemExit, ValueError):
        say("Pesquisa não iniciada. Confira os parâmetros/arquivo informado.")
        return
    if code:
        say("A execução foi interrompida ou teve cobertura incompleta. Consulte a auditoria preservada.")
    say(f"Pesquisa salva: {result['output']}")
    browse(result["output"])


def updates_menu(version):
    from abyss_updates import check_update, apply_update
    try:
        info = check_update(version, force=True)
        say(f"Versão instalada: {version} | Release estável: {info['latest']}\n{info['url']}")
        if not info["update_available"]:
            say("Nenhuma release mais recente disponível.")
        elif ask("Atualizar agora? s/N", "n").lower() == "s":
            result = apply_update(version)
            say("Atualizado. Encerre e reabra o ABYSS." if result.get("updated") else "Nenhuma atualização necessária.")
    except (OSError, ValueError, TimeoutError) as exc:
        say(str(exc) if isinstance(exc, ValueError) else "Não foi possível consultar o GitHub. Confira a conexão e tente novamente.")


def run_terminal(run, version, initial=None):
    say(f"\n  A B Y S S   v{version}\n  Inteligência além da superfície\n")
    if sys.stdin.isatty() and os.environ.get("ABYSS_NO_UPDATE_CHECK") != "1":
        from abyss_updates import check_update
        try:
            info = check_update(version)
            if info["update_available"]:
                say(f"NOVA RELEASE: {info['latest']}. Escolha [4] para atualizar.")
        except (OSError, ValueError, TimeoutError):
            say("Verificação de atualizações indisponível; pesquisa pode continuar normalmente.")
    try:
        if initial:
            try:
                browse(initial)
            except (OSError, ValueError) as exc:
                say(f"Não foi possível abrir a pesquisa ({type(exc).__name__}).")
                return 2
        while True:
            say("[1] Nova pesquisa  [2] Abrir pesquisa salva  [3] Retomar pesquisa  [4] Atualizações  [5] Configurar buscador  [0] Sair")
            choice = ask("Escolha")
            if choice == "0":
                return 0
            try:
                if choice == "1":
                    new_search(run)
                elif choice == "2":
                    browse(ask("Pasta da pesquisa ou research.json"))
                elif choice == "3":
                    path = ask("Caminho para research.json ou checkpoint.json")
                    queries = number("Consultas do plano a cobrir", 50, 1, 1000)
                    output = io.StringIO()
                    try:
                        with contextlib.redirect_stdout(output):
                            run(["--resume", str(Path(path).expanduser()), "--max-queries", str(queries)])
                        result = json.loads(output.getvalue())
                        browse(result["output"])
                    except (SystemExit, ValueError):
                        say("Não foi possível retomar; confira a pesquisa e a configuração do provedor.")
                elif choice == "4":
                    updates_menu(version)
                elif choice == "5":
                    from abyss_config import configure
                    configure()
            except (OSError, ValueError) as exc:
                say(f"Não foi possível abrir a pesquisa ({type(exc).__name__}).")
    except (EOFError, KeyboardInterrupt):
        say("\nABYSS encerrado.")
        return 0
