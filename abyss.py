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
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

VERSION = "0.1.0"
DIMENSIONS = {
    "institucional": ["história unidades endereço telefone", "relatório anual resultados", "CNPJ razão social", "diretoria governança"],
    "decisores": ["gerente engenharia manutenção", "coordenador automação industrial", "gerente infraestrutura TI", "segurança informação liderança"],
    "compras": ["compras MRO indiretos serviços", "suprimentos comprador", "cadastro fornecedores homologação", "Coupa Ariba portal fornecedores"],
    "tecnologia": ["automação SCADA supervisório", "sistemas industriais continuidade backup", "modernização transformação digital", "validação sistemas computadorizados"],
    "projetos": ["investimento expansão fábrica", "case automação integrador", "projeto engenharia industrial", "parceria fornecedor tecnologia"],
    "pessoas": ["site:linkedin.com/in manutenção", "site:linkedin.com/in compras suprimentos", "site:linkedin.com/in infraestrutura", "site:linkedin.com/in automação"],
    "vagas": ["vagas manutenção automação", "vagas compras serviços", "vagas validação qualificação equipamentos", "vagas infraestrutura segurança informação"],
    "documentos": ["filetype:pdf fornecedores", "filetype:pdf relatório anual", "filetype:pdf engenharia", "filetype:pdf sustentabilidade"],
    "noticias": ["notícias fábrica", "contrato serviços industriais", "evento engenharia manutenção", "prêmio eficiência operacional"],
}


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


def make_plan(company, location="", official_domains=(), aliases=()):
    queries = []
    for name in dict.fromkeys([company, *aliases]):
        for category, terms in DIMENSIONS.items():
            for term in terms:
                queries.append({"category": category, "query": f'"{name}" {location} {term}'.strip()})
    # Fontes corporativas sem restrição geográfica evitam perder compradores centrais.
    if location:
        for category in ("compras", "decisores"):
            for term in DIMENSIONS[category]:
                queries.append({"category": category, "query": f'"{company}" {term}'})
    for d in official_domains:
        for term in ("fornecedores", "contato unidades", "relatório anual", "engenharia tecnologia"):
            queries.append({"category": "institucional", "query": f"site:{d} {term}"})
    # Distribui dimensões no início; limites pequenos ainda cobrem vários temas.
    buckets = {}
    for q in queries:
        buckets.setdefault(q["category"], []).append(q)
    ordered = []
    while any(buckets.values()):
        for bucket in buckets.values():
            if bucket:
                ordered.append(bucket.pop(0))
    return ordered


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Não encaminha tokens de API para outro host.
        return None


def fetch_json(url, headers=None, timeout=25):
    request = Request(url, headers={"User-Agent": f"ABYSS/{VERSION}", "Accept": "application/json", **(headers or {})})
    with build_opener(NoRedirect()).open(request, timeout=timeout) as response:
        raw = response.read(4_000_001)
    if len(raw) > 4_000_000:
        raise ValueError("Resposta excede limite de 4 MB")
    return json.loads(raw)


def search(query, provider, count, searx_url=""):
    if provider == "brave":
        key = os.environ.get("BRAVE_API_KEY")
        if not key:
            raise ValueError("Configure BRAVE_API_KEY no ambiente; não grave a chave no projeto")
        data = fetch_json("https://api.search.brave.com/res/v1/web/search?" + urlencode({"q": query, "count": count}),
                          {"X-Subscription-Token": key})
        return [{"title": x.get("title", ""), "url": x.get("url", ""),
                 "snippet": x.get("description", ""), "published_date": x.get("page_age", "")}
                for x in data.get("web", {}).get("results", [])]
    if provider == "searxng":
        base = canonical_url(searx_url)
        parsed = urlsplit(base)
        if parsed.query:
            raise ValueError("SEARXNG_URL deve ser a URL base, sem parâmetros")
        if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("SearXNG remoto exige HTTPS")
        data = fetch_json(base.rstrip("/") + "/search?" + urlencode({"q": query, "format": "json", "language": "pt-BR"}))
        # Erros de motores não são equivalentes a pesquisa vazia bem-sucedida.
        if data.get("unresponsive_engines"):
            raise ValueError("SearXNG reportou motores indisponíveis; consulta incompleta")
        return [{"title": x.get("title", ""), "url": x.get("url", ""),
                 "snippet": x.get("content", ""), "published_date": x.get("publishedDate", "")}
                for x in data.get("results", [])[:count]]
    raise ValueError("Provedor desconhecido")


def ingest(store, results, query, category, provider, official_domains, imported=False):
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
                    "status": "nao_verificado_na_pagina_original"}
        if not any(all(e.get(k) == evidence[k] for k in ("title", "snippet", "query", "provider")) for e in store[item_id]["evidence"]):
            store[item_id]["evidence"].append(evidence)
    return skipped


def csv_safe(value):
    text = str(value or "")
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r")) else text


def save(output, target, plan, items, events, mode):
    output.mkdir(parents=True, exist_ok=False)
    bundle = {"schema_version": 1, "abyss_version": VERSION, "created_at": now(), "mode": mode,
              "target": target, "scope": "fontes publicas; sem contato; resultados nao exaustivos",
              "plan": plan, "sources": list(items.values()), "queries": events}
    (output / "research.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    with (output / "sources.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "url", "tipo_fonte", "categoria", "titulo", "trecho", "data_publicacao_informada", "coletado_em", "consulta", "provedor", "tipo_evidencia", "status"])
        for item in items.values():
            for e in item["evidence"]:
                w.writerow([csv_safe(v) for v in [item["id"], item["url"], item["source_kind"], e["category"], e["title"], e["snippet"], e["published_date_reported"], e["collected_at"], e["query"], e["provider"], e["evidence_type"], e["status"]]])
    manual = ["ABYSS — PLANO DE INVESTIGAÇÃO", f"Alvo: {target['company']} | Unidade: {target['location']}", ""]
    for q in plan:
        manual.extend([f"[{q['category']}] {q['query']}", "https://www.google.com/search?" + urlencode({"q": q["query"]}), ""])
    (output / "queries.txt").write_text("\n".join(manual), encoding="utf-8")
    failed = sum(e["status"] == "error" for e in events)
    report = [f"ABYSS {VERSION} — {target['company']}", f"Modo: {mode} | Unidade: {target['location']}",
              f"Fontes únicas: {len(items)} | Consultas executadas: {len(events)} | Falhas: {failed}",
              f"Consultas planejadas: {len(plan)} | Não executadas: {len(plan) - len(events)}", "",
              "LIMITES: trechos de buscadores e referências importadas não confirmam cargo atual, alçada,",
              "necessidade comercial ou homologação. Data de coleta não é data de publicação.",
              "Domínio oficial é informado pelo operador; não é autenticação da identidade empresarial.",
              "Nenhuma mensagem, formulário ou candidatura é enviada. Não há pontuação de confiança inventada.", ""]
    for item in items.values():
        report.extend([item["url"], f"Tipo: {item['source_kind']}"])
        for e in item["evidence"]:
            report.extend([f"  [{e['category']}] {e['title']}", f"  {e['snippet']}",
                           f"  Origem: {e['provider']} | {e['evidence_type']} | {e['status']}"])
        report.append("")
    for e in events:
        if e["status"] == "error":
            report.append(f"ERRO [{e['category']}]: {e['error']}")
    (output / "report.txt").write_text("\n".join(report), encoding="utf-8")
    checksums = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(output.iterdir()) if f.is_file()}
    (output / "sha256.json").write_text(json.dumps(checksums, indent=2), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description="ABYSS — inteligência de fontes abertas, somente leitura")
    parser.add_argument("--version", action="version", version=VERSION)
    parser.add_argument("--company", required=True)
    parser.add_argument("--location", default="")
    parser.add_argument("--domain", action="append", default=[])
    parser.add_argument("--alias", action="append", default=[])
    parser.add_argument("--provider", choices=["manual", "brave", "searxng"], default="manual")
    parser.add_argument("--searxng-url", default=os.environ.get("SEARXNG_URL", ""))
    parser.add_argument("--max-queries", type=int, default=9)
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--delay", type=float, default=2.0)
    parser.add_argument("--import-json", type=Path, help="Lista de resultados com title, url, snippet, category e query")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if not args.company.strip() or not 1 <= args.max_queries <= 1000 or not 1 <= args.count <= 20 or not 1 <= args.delay <= 60:
        parser.error("Empresa obrigatória; max-queries 1–1000; count 1–20; delay 1–60 segundos")
    if args.provider == "brave" and not os.environ.get("BRAVE_API_KEY"):
        parser.error("BRAVE_API_KEY ausente no ambiente")
    if args.provider == "searxng" and not args.searxng_url:
        parser.error("Informe --searxng-url ou SEARXNG_URL")
    try:
        domains = [domain(d) for d in args.domain]
        plan = make_plan(args.company, args.location, domains, args.alias)
        output = args.output or Path("output") / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        if output.exists():
            parser.error("Pasta de saída já existe; escolha outra para preservar evidências")
        items, events = {}, []
        if args.import_json:
            imported = json.loads(args.import_json.read_text(encoding="utf-8-sig"))
            if not isinstance(imported, list) or any(not isinstance(x, dict) for x in imported):
                raise ValueError("Importação exige uma lista JSON de objetos")
            for row in imported:
                skipped = ingest(items, [row], clean(row.get("query", "referencia fornecida")),
                                 clean(row.get("category", "referencia")), "import", domains, imported=True)
                if skipped:
                    raise ValueError("Importação contém URL inválida")
        if args.provider != "manual":
            for index, q in enumerate(plan[:args.max_queries]):
                if index:
                    time.sleep(args.delay)
                event = {**q, "at": now(), "status": "ok", "provider": args.provider}
                try:
                    results = search(q["query"], args.provider, args.count, args.searxng_url)
                    event["returned"] = len(results)
                    event["skipped"] = ingest(items, results, q["query"], q["category"], args.provider, domains)
                except HTTPError as exc:
                    event.update(status="error", error=f"HTTP {exc.code}; sem contornar bloqueio")
                    exc.close()
                except (ValueError, URLError, TimeoutError, OSError) as exc:
                    # Não serializa corpo, URL de erro ou headers: podem conter credenciais.
                    event.update(status="error", error=f"{type(exc).__name__}; conferir configuração/provedor")
                events.append(event)
                print(f"{index + 1}: {q['category']} — {event['status']}", file=sys.stderr)
                if event["status"] == "error":
                    break
        target = {"company": args.company, "location": args.location, "official_domains": domains, "aliases": args.alias}
        save(output, target, plan, items, events, args.provider)
        print(json.dumps({"output": str(output.resolve()), "sources": len(items), "planned_queries": len(plan),
                          "executed_queries": len(events), "errors": sum(e["status"] == "error" for e in events)}, ensure_ascii=False))
        return 2 if any(e["status"] == "error" for e in events) else 0
    except (ValueError, OSError) as exc:
        print(f"Erro local: {type(exc).__name__}. Confira arquivos e parâmetros.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
