"""Menu textual portátil: entrada padrão, saída padrão e nenhuma dependência."""
import contextlib
import io
import json
import os
import shutil
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
        say()


def browse(path):
    path, data = load_research(path)
    page, term = 0, ""
    say(f"\nALVO: {data['target'].get('company', '')} | {data['target'].get('location', '')}")
    say(f"Consultas: {len(data['queries'])}/{len(data['plan'])} | Falhas: {sum(q.get('status') == 'error' for q in data['queries'])}")
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
    say("[1] Brave API  [2] SearXNG  [3] Plano manual / importar referências")
    provider = {1: "brave", 2: "searxng", 3: "manual"}[number("Provedor", 3, 1, 3)]
    args += ["--provider", provider]
    if provider == "brave" and not os.environ.get("BRAVE_API_KEY"):
        say("BRAVE_API_KEY não está configurada. Defina a chave no ambiente e tente novamente.")
        return
    if provider == "searxng":
        endpoint = ask("URL da instância SearXNG", os.environ.get("SEARXNG_URL", "http://localhost:8080"))
        args += ["--searxng-url", endpoint]
    if provider != "manual":
        args += ["--max-queries", str(number("Limite de consultas", 9, 1, 1000)),
                 "--count", str(number("Resultados por consulta", 10, 1, 20))]
        say("A execução usa o provedor configurado e pode consumir sua cota.")
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
        say("O provedor apresentou erro. Os dados parciais e a auditoria foram preservados.")
    say(f"Pesquisa salva: {result['output']}")
    browse(result["output"])


def run_terminal(run, version, initial=None):
    say(f"\n  A B Y S S   v{version}\n  Inteligência além da superfície\n")
    try:
        if initial:
            try:
                browse(initial)
            except (OSError, ValueError) as exc:
                say(f"Não foi possível abrir a pesquisa ({type(exc).__name__}).")
                return 2
        while True:
            say("[1] Nova pesquisa  [2] Abrir pesquisa salva  [0] Sair")
            choice = ask("Escolha")
            if choice == "0":
                return 0
            try:
                if choice == "1":
                    new_search(run)
                elif choice == "2":
                    browse(ask("Pasta da pesquisa ou research.json"))
            except (OSError, ValueError) as exc:
                say(f"Não foi possível abrir a pesquisa ({type(exc).__name__}).")
    except (EOFError, KeyboardInterrupt):
        say("\nABYSS encerrado.")
        return 0
