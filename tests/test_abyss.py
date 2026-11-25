import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

import abyss


class ResearchTests(unittest.TestCase):
    def test_scope_and_corporate_purchasing(self):
        plan = abyss.make_plan("Empresa", "Anápolis", ["example.com"])
        self.assertEqual(len({q["category"] for q in plan[:9]}), 9)
        self.assertTrue(any(q["category"] == "compras" and q["scope"] == "corporativo" and "Anápolis" not in q["query"] for q in plan))
        self.assertTrue(any(q["query"].startswith("site:example.com") for q in plan))

    def test_dedup_preserves_different_evidence(self):
        records = {}
        for query in ["q1", "q2"]:
            abyss.ingest(records, [{"url": "https://example.com/a?utm_source=x", "snippet": query}], query, "compras", "brave", ["example.com"])
        self.assertEqual(len(records), 1)
        self.assertEqual(len(next(iter(records.values()))["evidence"]), 2)
        self.assertEqual(next(iter(records.values()))["source_kind"], "dominio_oficial_informado")
        self.assertEqual(abyss.source_kind("https://fakeexample.com", ["example.com"]), "terceiro")

    def test_invalid_sources_and_csv_formula(self):
        for url in ["javascript:alert(1)", "file:///etc/passwd", "https://user:secret@example.com"]:
            with self.assertRaises(ValueError):
                abyss.canonical_url(url)
        self.assertEqual(abyss.csv_safe(" =1+1"), "' =1+1")

    def test_brave_auth_and_mapping(self):
        fixture = {"web": {"results": [{"title": "T", "url": "https://example.com", "description": "D"}]}}
        with patch.dict("os.environ", {"BRAVE_API_KEY": "test-only"}), patch("abyss.fetch_json", return_value=fixture) as fetch:
            self.assertEqual(abyss.search("q", "brave", 3)[0]["snippet"], "D")
            self.assertEqual(fetch.call_args.args[1]["X-Subscription-Token"], "test-only")

    def test_searx_partial_failure_is_not_empty_success(self):
        with patch("abyss.fetch_json", return_value={"unresponsive_engines": [["engine", "timeout"]]}):
            with self.assertRaises(ValueError):
                abyss.search("q", "searxng", 10, "http://localhost:8080")

    def test_offline_export_and_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "run"
            code = abyss.main(["--company", "Example", "--domain", "example.com", "--import-json", "examples/reference.json", "--output", str(output)])
            self.assertEqual(code, 0)
            data = json.loads((output / "research.json").read_text())
            self.assertEqual(data["queries"], [])
            self.assertEqual(data["sources"][0]["evidence"][0]["evidence_type"], "imported_reference")
            for name, digest in json.loads((output / "sha256.json").read_text()).items():
                self.assertEqual(hashlib.sha256((output / name).read_bytes()).hexdigest(), digest)

    def test_http_failure_persists_audit_without_secrets(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {"BRAVE_API_KEY": "secret-fixture"}), patch("abyss.search", side_effect=HTTPError("https://api.invalid?token=secret-fixture", 429, "secret-fixture", {}, None)):
            output = Path(tmp) / "failed"
            code = abyss.main(["--company", "Example", "--provider", "brave", "--output", str(output)])
            self.assertEqual(code, 2)
            data = (output / "research.json").read_text()
            self.assertNotIn("secret-fixture", data)
            self.assertEqual(len(json.loads(data)["queries"]), 1)


if __name__ == "__main__":
    unittest.main()
