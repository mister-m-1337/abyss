#!/usr/bin/env python3
"""ABYSS: pesquisa comercial de fontes públicas, sem contato com o alvo."""
import argparse
import csv
import hashlib
import html
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler, HTTPSHandler
from abyss_discovery import build_plan, assess_sources
from abyss_network import tls_context

VERSION = "0.4.1"

def now():
    return datetime.now(timezone.utc).isoformat()


def clean(value):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", " ", str(value or "")))).strip()


def canonical_url(value):
    try:
        u = urlsplit(str(value).strip())
        if u.scheme not in {"https", "http"} or not u.hostname or u.username or u.password:
            raise ValueError("URL deve ser HTTP(S), sem credenciais")
        _ = u.port
        params = [(k, v) for k, v in parse_qsl(u.query, keep_blank_values=True)
                  if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid", "trk", "trackingid"}]
        return urlunsplit((u.scheme.lower(), u.netloc.lower(), u.path or "/", urlencode(params), ""))
    except (TypeError, ValueError) as exc:
        raise ValueError("URL inválida") from exc


def domain(value):
    host = urlsplit(value if "://" in value else "https://" + value).hostname
    if not host or not re.fullmatch(r"[a-zA-Z0-9.-]+", host):
        raise ValueError("Domínio oficial inválido")
    return host.lower().removeprefix("www.")


def source_kind(url, official_domains):
    host = domain(url)
    if any(host == d or host.endswith("." + d) for d in official_domains):
        return "dominio_oficial_informado"
    if host == "linkedin.com" or host.endswith(".linkedin.com"):
        return "perfil_ou_publicacao_profissional"
    if host == "theorg.com" or host.endswith(".theorg.com"):
        return "organograma_terceiro_nao_verificado"
    return "terceiro"


def make_plan(company, location="", official_domains=(), aliases=(), **options):
    return build_plan(company, location, official_domains, aliases, **options)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Não encaminha tokens de API para outro host.
        return None


def fetch_json(url, headers=None, timeout=25):
    request = Request(url, headers={"User-Agent": f"ABYSS/{VERSION}", "Accept": "application/json", **(headers or {})})
    with build_opener(NoRedirect(), HTTPSHandler(context=tls_context())).open(request, timeout=timeout) as response:
        raw = response.read(4_000_001)
    if len(raw) > 4_000_000:
        raise ValueError("Resposta excede limite de 4 MB")
    return json.loads(raw)


class SearchBatch(list):
    def __init__(self, rows, warnings=()):
        super().__init__(rows)
        self.warnings = list(warnings)


def search(query, provider, count, searx_url="", page=1, freshness="all"):
    if len(query) > 600 or len(query.split()) > 75:
        raise ValueError("Consulta excede limite de 600 caracteres/75 palavras")
    if provider == "brave":
        key = os.environ.get("BRAVE_API_KEY")
        if not key:
            raise ValueError("Configure BRAVE_API_KEY no ambiente; não grave a chave no projeto")
        params = {"q": query, "count": count, "offset": page - 1, "country": "BR", "extra_snippets": "true", "spellcheck": "false"}
        if freshness != "all":
            params["freshness"] = {"day": "pd", "month": "pm", "year": "py"}[freshness]
        data = fetch_json("https://api.search.brave.com/res/v1/web/search?" + urlencode(params),
                          {"X-Subscription-Token": key})
        if not isinstance(data, dict) or not isinstance(data.get("web", {}), dict):
            raise ValueError("Resposta Brave inválida")
        raw = data.get("web", {}).get("results", [])
        if not isinstance(raw, list):
            raise ValueError("Resultados Brave inválidos")
        return SearchBatch([{"title": x.get("title", ""), "url": x.get("url", ""),
                 "snippet": x.get("description", ""), "extra_snippets": x.get("extra_snippets", []), "published_date": x.get("page_age", "")}
                for x in raw if isinstance(x, dict)])
    if provider == "searxng":
        base = canonical_url(searx_url)
        parsed = urlsplit(base)
        if parsed.query:
            raise ValueError("SEARXNG_URL deve ser a URL base, sem parâmetros")
        if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("SearXNG remoto exige HTTPS")
        params = {"q": query, "format": "json", "language": "pt-BR", "pageno": page}
        if freshness != "all":
            params["time_range"] = freshness
        data = fetch_json(base.rstrip("/") + "/search?" + urlencode(params))
        if not isinstance(data, dict) or not isinstance(data.get("results", []), list):
            raise ValueError("Resposta SearXNG inválida")
        warnings = ["SearXNG: há motores indisponíveis; cobertura parcial"] if data.get("unresponsive_engines") else []
        if warnings and not data.get("results"):
            raise ValueError("SearXNG reportou motores indisponíveis; consulta incompleta")
        return SearchBatch([{"title": x.get("title", ""), "url": x.get("url", ""),
                 "snippet": x.get("content", ""), "published_date": x.get("publishedDate", "")}
                for x in data.get("results", [])[:count] if isinstance(x, dict)], warnings)
    raise ValueError("Provedor desconhecido")


def ingest(store, results, query, category, provider, official_domains, imported=False, page=1):
    skipped = 0
    for result in results:
        if not isinstance(result, dict):
            skipped += 1
            continue
        try:
            url = canonical_url(result.get("url", ""))
        except ValueError:
            skipped += 1
            continue
        item_id = hashlib.sha256(url.encode()).hexdigest()[:20]
        if item_id not in store:
            store[item_id] = {"id": item_id, "url": url, "source_kind": source_kind(url, official_domains),
                              "first_observed_at": now(), "evidence": []}
        evidence = {"title": clean(result.get("title")), "snippet": clean(result.get("snippet")),
                    "query": query, "category": category, "provider": provider,
                    "published_date_reported": clean(result.get("published_date")),
                    "collected_at": now(), "evidence_type": "imported_reference" if imported else "search_snippet",
                    "status": "nao_verificado_na_pagina_original", "page": page,
                    "extra_snippets": [clean(s) for s in result.get("extra_snippets", []) if isinstance(s, str)] if isinstance(result.get("extra_snippets", []), list) else []}
        if not any(all(e.get(k) == evidence[k] for k in ("title", "snippet", "query", "provider", "page", "extra_snippets")) for e in store[item_id]["evidence"]):
            store[item_id]["evidence"].append(evidence)
    return skipped


def csv_safe(value):
    text = str(value or "")
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r")) else text


def save(output, target, plan, items, events, mode, existing=False):
    output.mkdir(parents=True, exist_ok=existing)
    bundle = {"schema_version": 1, "abyss_version": VERSION, "created_at": now(), "mode": mode,
              "target": target, "scope": "fontes publicas; sem contato; resultados nao exaustivos",
              "plan": plan, "sources": list(items.values()), "queries": events}
    (output / "research.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    with (output / "sources.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "url", "tipo_fonte", "categoria", "titulo", "trecho", "data_publicacao_informada", "coletado_em", "consulta", "provedor", "tipo_evidencia", "status", "pagina", "trechos_adicionais", "sinais_alvo"])
        for item in items.values():
            for e in item["evidence"]:
                w.writerow([csv_safe(v) for v in [item["id"], item["url"], item["source_kind"], e["category"], e["title"], e["snippet"], e["published_date_reported"], e["collected_at"], e["query"], e["provider"], e["evidence_type"], e["status"], e.get("page", 1), " | ".join(e.get("extra_snippets", [])), json.dumps(item.get("target_signals", {}), ensure_ascii=False)]])
    manual = ["ABYSS — PLANO DE INVESTIGAÇÃO", f"Alvo: {target['company']} | Unidade: {target['location']}", ""]
    for q in plan:
        manual.extend([f"[{q['category']}] {q['query']}", "https://www.google.com/search?" + urlencode({"q": q["query"]}), ""])
    (output / "queries.txt").write_text("\n".join(manual), encoding="utf-8")
    failed = sum(e["status"] == "error" for e in events)
    report = [f"ABYSS {VERSION} — {target['company']}", f"Modo: {mode} | Unidade: {target['location']}",
              f"Fontes únicas: {len(items)} | Requisições registradas: {len(events)} | Falhas: {failed}",
              f"Consultas planejadas: {len(plan)} | Cobertura pode incluir múltiplas páginas/provedores", "",
              "LIMITES: trechos de buscadores e referências importadas não confirmam cargo atual, alçada,",
              "necessidade comercial ou homologação. Data de coleta não é data de publicação.",
              "Domínio oficial é informado pelo operador; não é autenticação da identidade empresarial.",
              "Nenhuma mensagem, formulário ou candidatura é enviada. Não há pontuação de confiança inventada.", ""]
    for item in items.values():
        report.extend([item["url"], f"Tipo: {item['source_kind']}"])
        for e in item["evidence"]:
            report.extend([f"  [{e['category']}] {e['title']}", f"  {e['snippet']}",
                           f"  Origem: {e['provider']} | {e['evidence_type']} | {e['status']}"])
            report.extend("  Trecho adicional: " + s for s in e.get("extra_snippets", []))
        report.append("")
        if item.get("target_signals"):
            report.append("Sinais para triagem (não confirmam vínculo): " + json.dumps(item["target_signals"], ensure_ascii=False))
    for e in events:
        if e["status"] == "error":
            report.append(f"ERRO [{e['category']}]: {e['error']}")
        for warning in e.get("warnings", []):
            report.append("COBERTURA PARCIAL: " + warning)
    (output / "report.txt").write_text("\n".join(report), encoding="utf-8")
    checksums = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(output.iterdir()) if f.is_file()}
    (output / "sha256.json").write_text(json.dumps(checksums, indent=2), encoding="utf-8")


def main(argv=None):
    from abyss_config import load_environment
    load_environment()
    parser = argparse.ArgumentParser(description="ABYSS — inteligência de fontes abertas, somente leitura")
    parser.add_argument("--version", action="version", version=VERSION)
    parser.add_argument("--check-update", action="store_true", help="Consultar a release estável mais recente")
    parser.add_argument("--update", action="store_true", help="Atualizar instalação Git pela release oficial")
    parser.add_argument("--install", action="store_true", help="Instalar o executável no perfil do usuário")
    parser.add_argument("--install-dir", type=Path, help="Pasta da instalação por usuário")
    parser.add_argument("--desktop-shortcut", action="store_true")
    parser.add_argument("--configure", action="store_true", help="Configurar o buscador nesta sessão")
    parser.add_argument("--company")
    parser.add_argument("--ui", action="store_true", help="Abrir interface interativa no terminal")
    parser.add_argument("--open", type=Path, help="Abrir uma pesquisa salva (pasta ou research.json)")
    parser.add_argument("--export", nargs="+", choices=["pdf", "xlsx"], help="Exportar relatório PDF e/ou Excel")
    parser.add_argument("--location", default="")
    parser.add_argument("--domain", action="append", default=[])
    parser.add_argument("--alias", action="append", default=[])
    parser.add_argument("--provider", choices=["manual", "brave", "searxng", "both"], default="manual")
    parser.add_argument("--searxng-url", default=os.environ.get("SEARXNG_URL", ""))
    parser.add_argument("--max-queries", type=int, default=9)
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--delay", type=float, default=2.0)
    parser.add_argument("--pages", type=int, default=None, help="Páginas por consulta/provedor, de 1 a 10")
    parser.add_argument("--max-requests", type=int, default=30, help="Limite total de chamadas novas ao provedor")
    parser.add_argument("--freshness", choices=["all", "day", "month", "year"], default=None)
    parser.add_argument("--depth", choices=["balanced", "deep"], default="balanced")
    parser.add_argument("--person", action="append", default=[], help="Profissional conhecido para revalidar vínculo/cargo")
    parser.add_argument("--keyword", action="append", default=[])
    parser.add_argument("--exclude-domain", action="append", default=[])
    parser.add_argument("--query-file", type=Path, help="TXT com consultas personalizadas, uma por linha")
    parser.add_argument("--resume", type=Path, help="Retomar research.json ou checkpoint.json em uma pasta nova")
    parser.add_argument("--import-json", type=Path, help="Lista de resultados com title, url, snippet, category e query")
    parser.add_argument("--output", type=Path)
    arguments = sys.argv[1:] if argv is None else argv
    args = parser.parse_args(arguments)
    if args.install or args.configure:
        try:
            if args.install:
                from abyss_installer import setup
                return setup(VERSION, args.install_dir, desktop=args.desktop_shortcut, run=main)
            from abyss_config import configure
            configure()
            if args.ui:
                from abyss_terminal import run_terminal
                return run_terminal(main, VERSION)
            return 0
        except (OSError, ValueError, EOFError, KeyboardInterrupt) as exc:
            print(str(exc) if isinstance(exc, ValueError) else "Instalação/configuração não concluída; confira o acesso à pasta.", file=sys.stderr)
            return 2
    if args.check_update or args.update:
        from abyss_updates import check_update, apply_update
        try:
            result = apply_update(VERSION) if args.update else check_update(VERSION, force=True)
            print(json.dumps(result, ensure_ascii=False))
            return 0
        except (OSError, ValueError, TimeoutError) as exc:
            print(str(exc) if isinstance(exc, ValueError) else "Não foi possível consultar/atualizar. Confira conexão, Git e permissões locais.", file=sys.stderr)
            return 2
    if args.ui or (not arguments and sys.stdin.isatty()):
        from abyss_terminal import run_terminal
        return run_terminal(main, VERSION, args.open)
    if args.open:
        if args.export:
            from abyss_exports import export_research
            try:
                files = export_research(args.open, args.export)
                print(json.dumps({"exports": [str(f.resolve()) for f in files]}, ensure_ascii=False))
                return 0
            except (ValueError, OSError) as exc:
                print(f"Exportação falhou: {type(exc).__name__}. Confira a pesquisa e o acesso à pasta.", file=sys.stderr)
                return 2
        from abyss_terminal import run_terminal
        return run_terminal(main, VERSION, args.open)
    resumed = None
    if args.resume:
        from abyss_exports import load_research
        try:
            _, resumed = load_research(args.resume)
            old = resumed["target"]
            if args.company and args.company != old.get("company"):
                parser.error("Retomada deve manter a empresa original")
            args.company = old["company"]
            if args.location and args.location != old.get("location", ""):
                parser.error("Retomada deve manter a localidade original")
            args.location = old.get("location", "")
            args.domain = old.get("official_domains", [])
            args.alias = old.get("aliases", [])
            if args.provider == "manual":
                args.provider = resumed.get("mode", "manual")
            args.freshness = args.freshness or old.get("search_settings", {}).get("freshness", "all")
            args.pages = old.get("search_settings", {}).get("pages", 1) if args.pages is None else args.pages
        except (ValueError, OSError, KeyError):
            parser.error("Não foi possível abrir a pesquisa para retomada")
    args.freshness = args.freshness or "all"
    args.pages = 1 if args.pages is None else args.pages
    if not args.company:
        if not arguments:
            parser.print_help()
            return 0
        parser.error("Informe --company, --ui ou --open")
    if not args.company.strip() or not 1 <= args.max_queries <= 1000 or not 1 <= args.count <= 20 or not 1 <= args.delay <= 60:
        parser.error("Empresa obrigatória; max-queries 1–1000; count 1–20; delay 1–60 segundos")
    if not 1 <= args.pages <= 10 or not 1 <= args.max_requests <= 1000:
        parser.error("pages deve ser 1–10 e max-requests 1–1000")
    if args.provider in {"brave", "both"} and not os.environ.get("BRAVE_API_KEY"):
        parser.error("BRAVE_API_KEY ausente no ambiente")
    if args.provider in {"searxng", "both"} and not args.searxng_url:
        parser.error("Informe --searxng-url ou SEARXNG_URL")
    try:
        domains = [domain(d) for d in args.domain]
        custom = args.query_file.read_text(encoding="utf-8-sig").splitlines() if args.query_file else []
        plan = resumed["plan"] if resumed else make_plan(args.company, args.location, domains, args.alias, depth=args.depth,
                     people=args.person, keywords=args.keyword, excluded=[domain(d) for d in args.exclude_domain],
                     custom=[q for q in custom if q.strip() and not q.lstrip().startswith("#")])
        if any(not isinstance(q.get("query"), str) or len(q["query"]) > 600 or len(q["query"].split()) > 75 for q in plan):
            parser.error("Plano contém consulta inválida ou longa demais (máximo 600 caracteres/75 palavras)")
        output = args.output or Path("output") / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        if output.exists():
            parser.error("Pasta de saída já existe; escolha outra para preservar evidências")
        items = {s["id"]: s for s in resumed["sources"]} if resumed else {}
        events = list(resumed["queries"]) if resumed else []
        if args.import_json:
            imported = json.loads(args.import_json.read_text(encoding="utf-8-sig"))
            if not isinstance(imported, list) or any(not isinstance(x, dict) for x in imported):
                raise ValueError("Importação exige uma lista JSON de objetos")
            for row in imported:
                skipped = ingest(items, [row], clean(row.get("query", "referencia fornecida")),
                                 clean(row.get("category", "referencia")), "import", domains, imported=True)
                if skipped:
                    raise ValueError("Importação contém URL inválida")
        target = {"company": args.company, "location": args.location, "official_domains": domains, "aliases": args.alias}
        target["search_settings"] = {"pages": args.pages, "freshness": args.freshness, "depth": args.depth}
        output.mkdir(parents=True, exist_ok=False)
        from abyss_engine import execute, checkpoint, unresolved_errors
        persist = lambda: checkpoint(output / "checkpoint.json", target, plan, items, events, args.provider)
        persist()
        execution = {"requests_this_run": 0, "stop_reason": "manual_plan"}
        if args.provider != "manual":
            providers = ["brave", "searxng"] if args.provider == "both" else [args.provider]
            progress = lambda e, count: print(f"{len(events)}: {e['category']} | {e['provider']} p{e['page']} — {e['status']} | {e.get('returned', 0)} resultados | {count} fontes", file=sys.stderr)
            execution = execute(plan, items, events, providers, args, search, ingest, domains, persist, progress, now)
        target["execution"] = execution
        items = assess_sources(items, args.company, args.alias, args.location)
        save(output, target, plan, items, events, args.provider, existing=True)
        if args.export:
            from abyss_exports import export_research
            exported = export_research(output, args.export)
        else:
            exported = []
        print(json.dumps({"output": str(output.resolve()), "sources": len(items), "planned_queries": len(plan),
                          "executed_queries": len(events), "errors": unresolved_errors(events), **execution,
                          "exports": [str(f.resolve()) for f in exported]}, ensure_ascii=False))
        return 130 if execution["stop_reason"] == "interrupted" else (2 if unresolved_errors(events) else 0)
    except (ValueError, OSError) as exc:
        print(f"Erro local: {type(exc).__name__}. Confira arquivos e parâmetros.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    if getattr(sys, "frozen", False) and len(sys.argv) == 1:
        from abyss_installer import installed_root, setup
        if not installed_root():
            try:
                sys.exit(setup(VERSION, guided=True, run=main))
            except (ValueError, OSError, EOFError, KeyboardInterrupt) as exc:
                print(str(exc) if isinstance(exc, ValueError) else "Instalação interrompida.", file=sys.stderr)
                sys.exit(2)
    sys.exit(main())
