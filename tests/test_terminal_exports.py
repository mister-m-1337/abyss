import contextlib
import hashlib
import io
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import abyss
import abyss_exports as exports
import abyss_terminal as terminal


def research(folder, snippet="Evidência pública de manutenção e recuperação."):
    items = {}
    abyss.ingest(items, [{"url": "https://example.com/fornecedores", "title": "Aché — Anápolis", "snippet": snippet}],
                 "empresa fornecedores", "compras", "fixture", ["example.com"], imported=True)
    abyss.save(folder, {"company": "Aché", "location": "Anápolis GO"}, abyss.make_plan("Aché"), items, [], "manual")
    return folder / "research.json"


class ExportTests(unittest.TestCase):
    def test_excel_valid_package_and_untrusted_content_is_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = research(Path(tmp) / "run", '=HYPERLINK("bad")\x1b[31m & <texto> 中文')
            files = exports.export_research(path, ["xlsx"])
            with ZipFile(files[0]) as z:
                self.assertIsNone(z.testzip())
                for name in z.namelist():
                    ET.fromstring(z.read(name))
                ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
                workbook = ET.fromstring(z.read("xl/workbook.xml"))
                self.assertEqual([s.attrib["name"] for s in workbook.findall("s:sheets/s:sheet", ns)], ["Resumo", "Fontes", "Consultas", "Plano"])
                sources = ET.fromstring(z.read("xl/worksheets/sheet2.xml"))
                self.assertEqual(sources.findall(".//s:f", ns), [])
                texts = [t.text or "" for t in sources.findall(".//s:t", ns)]
                self.assertTrue(any(t.startswith('=HYPERLINK') for t in texts))
                self.assertTrue(any("中文" in t for t in texts))
                self.assertNotIn(b"\x1b", z.read("xl/worksheets/sheet2.xml"))

    def test_pdf_pagination_xref_and_accents(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = research(Path(tmp) / "run", "Ação técnica de recuperação. " * 500)
            pdf = exports.export_research(path, ["pdf"])[0].read_bytes()
            self.assertTrue(pdf.startswith(b"%PDF-1.4"))
            self.assertIn("Aché".encode("cp1252"), pdf)
            count = int(re.search(rb"/Count (\d+)", pdf).group(1))
            self.assertGreater(count, 2)
            offset = int(re.search(rb"startxref\n(\d+)", pdf).group(1))
            self.assertEqual(pdf[offset:offset + 4], b"xref")
            section = pdf[offset:].split(b"trailer")[0].splitlines()
            for index, entry in enumerate(section[3:], 1):
                position = int(entry[:10])
                self.assertTrue(pdf[position:].startswith(f"{index} 0 obj".encode()))

    def test_exports_preserve_original_and_bind_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = research(Path(tmp) / "run")
            original = (path.parent / "sha256.json").read_bytes()
            first = exports.export_research(path, ["pdf", "xlsx"])
            second = exports.export_research(path, ["pdf"])
            self.assertNotEqual(first[0].parent, second[0].parent)
            manifest = json.loads((first[0].parent / "sha256.json").read_text())
            self.assertEqual(manifest["research_sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual((path.parent / "sha256.json").read_bytes(), original)
            for file in first:
                self.assertEqual(manifest["files"][file.name], hashlib.sha256(file.read_bytes()).hexdigest())

    def test_cli_export_existing_research_without_network(self):
        with tempfile.TemporaryDirectory() as tmp, patch("abyss.search") as search, contextlib.redirect_stdout(io.StringIO()) as output:
            path = research(Path(tmp) / "run")
            self.assertEqual(abyss.main(["--open", str(path), "--export", "pdf", "xlsx"]), 0)
            self.assertEqual(len(json.loads(output.getvalue())["exports"]), 2)
            search.assert_not_called()

    def test_invalid_input_does_not_create_exports(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text('{"target":{},"sources":[null],"queries":[],"plan":[]}')
            with self.assertRaises(ValueError):
                exports.export_research(path, ["pdf"])
            self.assertEqual(len(list(Path(tmp).iterdir())), 1)


class TerminalTests(unittest.TestCase):
    def test_new_search_wizard_displays_provider_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            previous = Path.cwd()
            answers = ["Empresa teste", "Anápolis", "example.com", "", "2", "http://localhost:8080", "1", "2", "", "0", "0"]
            try:
                os.chdir(tmp)
                with patch("builtins.input", side_effect=answers), patch("abyss.search", return_value=[{"title": "Resultado do provedor", "url": "https://example.com/case", "snippet": "Evidência de projeto"}]) as search, contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(terminal.run_terminal(abyss.main, abyss.VERSION), 0)
                search.assert_called_once()
                self.assertIn("Resultado do provedor", output.getvalue())
                saved = list(Path("output").glob("*/research.json"))
                self.assertEqual(len(saved), 1)
                self.assertEqual(json.loads(saved[0].read_text())["queries"][0]["returned"], 1)
            finally:
                os.chdir(previous)

    def test_browse_filter_detail_and_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = research(Path(tmp) / "run")
            answers = ["2", str(path), "f", "compras", "d", "1", "", "3", "", "0", "0"]
            with patch("builtins.input", side_effect=answers), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(terminal.run_terminal(abyss.main, abyss.VERSION), 0)
            self.assertIn("Evidência pública", output.getvalue())
            self.assertIn("Exportado:", output.getvalue())
            self.assertEqual(len(list(path.parent.glob("export-*/*.pdf"))), 1)
            self.assertEqual(len(list(path.parent.glob("export-*/*.xlsx"))), 1)

    def test_terminal_control_sequences_are_removed(self):
        value = exports.visible("Título\x1b[2J\x1b]0;alterado\x07normal\x00")
        self.assertEqual(value, "Títulonormal")

    def test_invalid_initial_path_returns_error(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(terminal.run_terminal(abyss.main, abyss.VERSION, "/nonexistent-abyss/research.json"), 2)

    def test_pagination_retains_original_source_numbers(self):
        data = {"sources": [{"url": f"https://example.com/{i}", "evidence": [{"title": f"Fonte {i}", "category": "compras"}]} for i in range(12)]}
        with contextlib.redirect_stdout(io.StringIO()) as output:
            page, pages = terminal.display_sources(data, page=1)
        self.assertEqual((page, pages), (1, 2))
        self.assertIn("  9 ", output.getvalue())
        self.assertNotIn("Fonte 0\n", output.getvalue())


if __name__ == "__main__":
    unittest.main()
