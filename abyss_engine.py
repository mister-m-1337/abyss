"""Execução limitada e retomável das consultas, páginas e provedores."""
import json
import time
from urllib.error import HTTPError, URLError


def request_key(event):
    return (event["query"], event["provider"], event.get("page", 1), event.get("freshness", "all"))


def unresolved_errors(events):
    latest = {request_key(e): e for e in events}
    return sum(e["status"] in {"error", "partial"} for e in latest.values())


def checkpoint(path, target, plan, items, events, mode):
    from datetime import datetime, timezone
    state = {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
             "mode": mode, "target": target, "plan": plan, "sources": list(items.values()), "queries": events}
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def execute(plan, items, events, providers, args, search, ingest, domains, persist, progress, clock):
    completed = {request_key(e) for e in events if e["status"] == "ok"}
    exhausted = {(e["query"], e["provider"]) for e in events if e["status"] == "ok" and e.get("returned") == 0 and e.get("freshness", "all") == args.freshness}
    disabled = set()
    requests = 0
    reason = "plan_complete"
    try:
        for query in plan[:args.max_queries]:
            for page in range(1, args.pages + 1):
                for provider in providers:
                    event = {**query, "at": clock(), "provider": provider, "page": page, "freshness": args.freshness, "status": "ok"}
                    if provider in disabled or (query["query"], provider) in exhausted or request_key(event) in completed:
                        continue
                    if requests >= args.max_requests:
                        return {"requests_this_run": requests, "stop_reason": "request_limit"}
                    if requests:
                        time.sleep(args.delay)
                    requests += 1
                    try:
                        results = search(query["query"], provider, args.count, args.searxng_url, page=page, freshness=args.freshness)
                        event["returned"] = len(results)
                        event["skipped"] = ingest(items, results, query["query"], query["category"], provider, domains, page=page)
                        event["warnings"] = list(getattr(results, "warnings", []))
                        if event["skipped"]:
                            event["warnings"].append("Resultados com URL inválida foram ignorados")
                        if event["warnings"]:
                            event["status"] = "partial"
                        elif not results:
                            exhausted.add((query["query"], provider))
                    except HTTPError as exc:
                        event.update(status="error", error=f"HTTP {exc.code}; provedor suspenso nesta execução")
                        exc.close()
                        disabled.add(provider)
                    except (ValueError, URLError, TimeoutError, OSError, TypeError) as exc:
                        event.update(status="error", error=f"{type(exc).__name__}; conferir configuração/provedor")
                        disabled.add(provider)
                    events.append(event)
                    persist()
                    progress(event, len(items))
                if len(disabled) == len(providers):
                    return {"requests_this_run": requests, "stop_reason": "providers_unavailable"}
        if args.max_queries < len(plan):
            reason = "query_limit"
    except KeyboardInterrupt:
        reason = "interrupted"
        persist()
    return {"requests_this_run": requests, "stop_reason": reason}
