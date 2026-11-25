"""Planejamento e sinais explicáveis de relação com o alvo; sem inferência de fatos."""
import re
import unicodedata
from urllib.parse import urlsplit


TERMS = {
    "institucional": ['(unidades OR endereço OR contato)', '"relatório anual"', '(CNPJ OR "razão social")', '(diretoria OR governança)'],
    "decisores": ['("gerente de engenharia" OR "coordenador de manutenção")', '"automação industrial" (gerente OR coordenador)', '(infraestrutura OR TI) (gerente OR diretor)', '"segurança da informação" liderança'],
    "compras": ['(compras OR MRO OR suprimentos)', '"comprador" "serviços"', '("cadastro de fornecedores" OR homologação)', '(Coupa OR Ariba OR "portal de fornecedores")'],
    "tecnologia": ['(SCADA OR supervisório OR automação)', '(backup OR "continuidade operacional")', '(modernização OR "transformação digital")', '"validação de sistemas computadorizados"'],
    "projetos": ['(investimento OR expansão) fábrica', 'case automação', '(projeto OR engenharia) industrial', '(parceria OR fornecedor) tecnologia'],
    "pessoas": ['site:linkedin.com/in manutenção', 'site:linkedin.com/in compras', 'site:linkedin.com/in infraestrutura', 'site:linkedin.com/posts automação'],
    "vagas": ['vagas (manutenção OR automação)', 'vagas (compras OR suprimentos)', 'vagas (validação OR qualificação)', 'vagas (infraestrutura OR segurança)'],
    "documentos": ['filetype:pdf fornecedores', 'filetype:pdf "relatório anual"', 'filetype:pdf engenharia', 'filetype:pdf sustentabilidade'],
    "noticias": ['notícias fábrica', 'contrato "serviços industriais"', 'evento (engenharia OR manutenção)', '"eficiência operacional"'],
}


def phrase(value):
    return '"' + re.sub(r'["\r\n]', ' ', value).strip() + '"'


def build_plan(company, location="", domains=(), aliases=(), depth="balanced", people=(), keywords=(), excluded=(), custom=()):
    buckets = {k: [] for k in TERMS}
    seen = set()
    suffix = " ".join(f"-site:{d}" for d in excluded)

    def add(category, query, scope):
        query = " ".join((query + " " + suffix).split())
        if query.casefold() not in seen:
            seen.add(query.casefold())
            buckets.setdefault(category, []).append({"category": category, "query": query, "scope": scope})

    for name in dict.fromkeys([company, *aliases]):
        for category, terms in TERMS.items():
            for index, term in enumerate(terms):
                # Mistura consultas locais e corporativas em todas as dimensões.
                local = location if index % 2 == 0 else ""
                add(category, f"{phrase(name)} {local} {term}", "unidade" if local else "corporativo")
            if location:
                add(category, f"{phrase(name)} {terms[0]}", "corporativo")
            if depth == "deep":
                for term in terms:
                    add(category, f"{phrase(name)} {location} {term}", "unidade" if location else "corporativo")
        if depth == "deep":
            for term in ['(maintenance OR engineering) (manager OR director)', '(procurement OR sourcing) services', '(OT OR ICS) cybersecurity', 'case study industrial', '(supplier OR vendor) registration']:
                add("internacional", f"{phrase(name)} {term}", "corporativo")
    for d in domains:
        for term in ['fornecedores', 'contato unidades', '"relatório anual"', 'engenharia tecnologia']:
            add("institucional", f"site:{d} {term}", "oficial")
    for person in people:
        for term in ["", '(cargo OR gerente OR coordenador)', '("novo ciclo" OR "nova jornada" OR despedida)']:
            add("pessoas", f"{phrase(person)} {phrase(company)} {term}", "pessoa_informada")
    for keyword in keywords:
        add("especifica", f"{phrase(company)} {location} {phrase(keyword)}", "tema_informado")
    for query in custom:
        add("personalizada", query, "consulta_informada")
    # Pedidos explícitos do operador aparecem antes das consultas genéricas.
    output = [q for bucket in buckets.values() for q in bucket if q["scope"] in {"pessoa_informada", "tema_informado", "consulta_informada"}]
    for category, bucket in buckets.items():
        buckets[category] = [q for q in bucket if q["scope"] not in {"pessoa_informada", "tema_informado", "consulta_informada"}]
    while any(buckets.values()):
        for bucket in buckets.values():
            if bucket:
                output.append(bucket.pop(0))
    return output


def normalize(text):
    return " ".join(re.findall(r"\w+", ''.join(c for c in unicodedata.normalize("NFKD", text.casefold()) if not unicodedata.combining(c))))


def assess_sources(items, company, aliases=(), location=""):
    names = [company, *aliases]
    for source in items.values():
        # A própria consulta NÃO é evidência de que a fonte fala sobre o alvo.
        text = normalize(" ".join(str(e.get(k, "")) for e in source["evidence"] for k in ("title", "snippet")))
        text += " " + normalize(" ".join(s for e in source["evidence"] for s in e.get("extra_snippets", [])))
        matched = [n for n in names if normalize(n) and f" {normalize(n)} " in f" {text} "]
        location_tokens = normalize(location).split()
        source["target_signals"] = {
            "official_domain": source.get("source_kind") == "dominio_oficial_informado",
            "names_in_title_or_snippet": matched,
            "location_in_title_or_snippet": bool(location_tokens) and all(t in text.split() for t in location_tokens),
            "review_required": True,
        }
    # Ordenação para triagem, sem apresentar uma pontuação como certeza factual.
    return dict(sorted(items.items(), key=lambda pair: (
        not pair[1]["target_signals"]["official_domain"],
        not bool(pair[1]["target_signals"]["names_in_title_or_snippet"]),
        not pair[1]["target_signals"]["location_in_title_or_snippet"],
    )))
