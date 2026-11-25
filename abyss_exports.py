"""Exportadores PDF e Excel OOXML sem dependências externas."""
import hashlib
import json
import re
import textwrap
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile


def visible(value):
    """Remove controles de terminal/XML, preservando texto legível."""
    text = str(value if value is not None else "")
    text = re.sub(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)", "", text)
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    return "".join(c for c in text if c in "\n\t" or (ord(c) >= 32 and not 127 <= ord(c) <= 159 and ord(c) not in {0xfffe, 0xffff} and not 0xd800 <= ord(c) <= 0xdfff))


def load_research(path):
    path = Path(path).expanduser()
    if path.is_dir():
        path /= "research.json"
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or not isinstance(data.get("target"), dict):
        raise ValueError("Arquivo não é uma pesquisa ABYSS")
    if not isinstance(data.get("sources"), list) or not isinstance(data.get("queries"), list) or not isinstance(data.get("plan"), list):
        raise ValueError("Estrutura de pesquisa inválida")
    for source in data["sources"]:
        if not isinstance(source, dict) or not isinstance(source.get("evidence"), list) or not isinstance(source.get("url"), str):
            raise ValueError("Fonte inválida no arquivo de pesquisa")
        if any(not isinstance(e, dict) for e in source["evidence"]):
            raise ValueError("Evidência inválida no arquivo de pesquisa")
    if any(not isinstance(q, dict) for q in data["queries"] + data["plan"]):
        raise ValueError("Consulta inválida no arquivo de pesquisa")
    return path, data


def evidence_rows(data):
    for source in data["sources"]:
        for e in source["evidence"]:
            yield [source.get("id", ""), source["url"], source.get("source_kind", ""),
                   e.get("category", ""), e.get("title", ""), e.get("snippet", ""),
                   e.get("published_date_reported", ""), e.get("collected_at", ""),
                   e.get("query", ""), e.get("provider", ""), e.get("evidence_type", ""), e.get("status", "")]


def workbook_tables(data):
    errors = sum(q.get("status") == "error" for q in data["queries"])
    summary = [
        ["ABYSS", "Inteligência além da superfície"],
        ["Empresa", data["target"].get("company", "")],
        ["Localidade", data["target"].get("location", "")],
        ["Coleta UTC", data.get("created_at", "")],
        ["Modo", data.get("mode", "")],
        ["Fontes únicas", len(data["sources"])],
        ["Consultas planejadas", len(data["plan"])],
        ["Consultas executadas", len(data["queries"])],
        ["Falhas", errors],
        ["Validação", "Trechos de busca/importações; cargos, datas e autoridade exigem confirmação na fonte."],
        ["Contato com alvo", "Nenhuma mensagem, proposta ou cadastro enviado."],
        ["Excel", "Texto longo pode ser truncado em 32.767 caracteres por célula. Conteúdo integral no JSON original."],
    ]
    sources = [["ID", "URL", "Tipo de fonte", "Categoria", "Título", "Evidência", "Publicação informada", "Coleta UTC", "Consulta", "Provedor", "Tipo de evidência", "Status"], *evidence_rows(data)]
    queries = [["Categoria", "Consulta", "Status", "Resultados", "Ignorados", "Erro", "Coleta UTC"]]
    queries.extend([[q.get(k, "") for k in ("category", "query", "status", "returned", "skipped", "error", "at")] for q in data["queries"]])
    plan = [["Categoria", "Consulta"], *[[q.get("category", ""), q.get("query", "")] for q in data["plan"]]]
    return [("Resumo", summary), ("Fontes", sources), ("Consultas", queries), ("Plano", plan)]


def column_name(index):
    name = ""
    while index:
        index, rem = divmod(index - 1, 26)
        name = chr(65 + rem) + name
    return name


def xlsx_sheet(rows):
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    ET.register_namespace("", ns)
    root = ET.Element(f"{{{ns}}}worksheet")
    views = ET.SubElement(root, "sheetViews")
    view = ET.SubElement(views, "sheetView", workbookViewId="0")
    ET.SubElement(view, "pane", ySplit="1", topLeftCell="A2", activePane="bottomLeft", state="frozen")
    cols = ET.SubElement(root, "cols")
    count = max((len(r) for r in rows), default=1)
    for col in range(1, count + 1):
        ET.SubElement(cols, "col", min=str(col), max=str(col), width="64" if col in {2, 6, 9} else "28", customWidth="1")
    body = ET.SubElement(root, "sheetData")
    for row_index, row in enumerate(rows, 1):
        row_xml = ET.SubElement(body, "row", r=str(row_index))
        for col, value in enumerate(row, 1):
            cell = ET.SubElement(row_xml, "c", r=f"{column_name(col)}{row_index}", s="1" if row_index == 1 else "0")
            if isinstance(value, (int, float)):
                ET.SubElement(cell, "v").text = str(value)
            else:
                # inlineStr impede execução de fórmulas vindas de conteúdo externo.
                cell.set("t", "inlineStr")
                content = ET.SubElement(ET.SubElement(cell, "is"), "t")
                content.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                content.text = visible(value)[:32767]
    if len(rows) > 1:
        ET.SubElement(root, "autoFilter", ref=f"A1:{column_name(count)}{len(rows)}")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def write_xlsx(path, data):
    tables = workbook_tables(data)
    if any(len(rows) > 1_048_576 for _, rows in tables):
        raise ValueError("Pesquisa excede o limite de linhas do Excel")
    content = '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
    for i in range(1, len(tables) + 1):
        content += f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    content += "</Types>"
    workbook = '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
    relationships = '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    for i, (name, _) in enumerate(tables, 1):
        workbook += f'<sheet name="{name}" sheetId="{i}" r:id="rId{i}"/>'
        relationships += f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
    workbook += "</sheets></workbook>"
    relationships += '<Relationship Id="styles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'
    styles = '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF102A43"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'
    with ZipFile(path, "x", ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content)
        z.writestr("_rels/.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", relationships)
        z.writestr("xl/styles.xml", styles)
        for i, (_, rows) in enumerate(tables, 1):
            z.writestr(f"xl/worksheets/sheet{i}.xml", xlsx_sheet(rows))


def pdf_text(value):
    # Fontes PDF padrão WinAnsi suportam português. Outros alfabetos viram '?'.
    text = visible(value).encode("cp1252", "replace")
    return text.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def report_lines(data):
    target = data["target"]
    yield "RELATÓRIO DE INTELIGÊNCIA DE FONTES ABERTAS"
    yield f"Empresa: {target.get('company', '')}"
    yield f"Localidade: {target.get('location', '')}"
    yield f"Pesquisa coletada em UTC: {data.get('created_at', '')}"
    yield f"Modo: {data.get('mode', '')} | Fontes únicas: {len(data['sources'])}"
    yield f"Consultas: {len(data['queries'])} executadas / {len(data['plan'])} planejadas"
    yield ""
    yield "Trechos de buscadores e referências importadas exigem validação na fonte original."
    yield "Não confirmam cargo atual, poder de contratação ou demanda comercial."
    yield "Nenhuma mensagem, proposta ou cadastro foi enviado pela ferramenta."
    yield "PDF utiliza caracteres WinAnsi (português); outros alfabetos: consultar JSON/Excel."
    yield ""
    if not data["sources"]:
        yield "Nenhum resultado coletado. Consulte o plano de buscas e os erros registrados."
    for index, source in enumerate(data["sources"], 1):
        yield f"FONTE {index} | {source.get('source_kind', '')}"
        yield source["url"]
        for e in source["evidence"]:
            yield f"Categoria: {e.get('category', '')} | {e.get('title', '')}"
            yield f"Evidência: {e.get('snippet', '')}"
            yield f"Publicação informada: {e.get('published_date_reported') or 'não informada'}"
            yield f"Coleta UTC: {e.get('collected_at', '')}"
            yield f"Consulta: {e.get('query', '')}"
            yield f"Origem: {e.get('provider', '')} | {e.get('evidence_type', '')}"
            yield f"Status: {e.get('status', '')}"
        yield ""
    yield "CONSULTAS EXECUTADAS"
    for q in data["queries"]:
        yield f"[{q.get('status', '')}] {q.get('query', '')}"
        if q.get("error"):
            yield f"Erro: {q['error']}"
    yield ""
    yield "PLANO DE BUSCAS"
    for q in data["plan"]:
        yield f"[{q.get('category', '')}] {q.get('query', '')}"


def write_pdf(path, data):
    lines = []
    for text in report_lines(data):
        lines.extend(textwrap.wrap(visible(text), width=88, replace_whitespace=True) or [""])
    pages = [lines[i:i + 51] for i in range(0, len(lines), 51)]
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>"]
    kids = []
    for index, page in enumerate(pages, 1):
        page_id = len(objects) + 1
        kids.append(f"{page_id} 0 R")
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> /Contents {page_id + 1} 0 R >>".encode())
        stream = b"0.06 0.16 0.26 rg 0 774 595 68 re f\n0.2 0.85 0.8 rg BT /F1 24 Tf 42 797 Td (ABYSS) Tj ET\n"
        stream += b"0.1 0.15 0.2 rg BT /F1 9 Tf 42 750 Td 13 TL\n"
        for line in page:
            stream += b"(" + pdf_text(line) + b") Tj T*\n"
        stream += b"ET\n0.35 0.4 0.45 rg BT /F1 8 Tf 42 40 Td (" + pdf_text(f"ABYSS | Fontes públicas | Página {index}/{len(pages)}") + b") Tj ET\n"
        objects.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"endstream")
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(pages)} >>".encode()
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode() + obj + b"\nendobj\n")
    start = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode())
    with Path(path).open("xb") as f:
        f.write(output)


def export_research(research_path, formats):
    path, data = load_research(research_path)
    requested = list(dict.fromkeys(formats))
    if any(f not in {"pdf", "xlsx"} for f in requested):
        raise ValueError("Formatos disponíveis: pdf, xlsx")
    # Subpasta nova preserva pesquisa original e seu manifesto de hashes.
    import tempfile
    folder = Path(tempfile.mkdtemp(prefix="export-", dir=path.parent))
    files = []
    for fmt in requested:
        file = folder / f"abyss-report.{fmt}"
        (write_pdf if fmt == "pdf" else write_xlsx)(file, data)
        files.append(file)
    manifest = {"research_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "files": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    (folder / "sha256.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return files
