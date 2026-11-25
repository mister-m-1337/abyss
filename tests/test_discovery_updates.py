import contextlib
import io
import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

import abyss
import abyss_discovery as discovery
import abyss_updates as updates
import abyss_terminal as terminal


class DiscoveryTests(unittest.TestCase):
    def test_plan_variants_custom_names_and_exclusions(self):
        plan = discovery.build_plan("Aché", "Anápolis", ["ache.com.br"], ["Aché"], depth="deep", people=["Pessoa Teste"], keywords=["WinCC"], excluded=["ruido.example"], custom=['"Aché" automação'])
        self.assertEqual(len({q["query"] for q in plan}), len(plan))
        self.assertTrue(all("-site:ruido.example" in q["query"] for q in plan))
        self.assertTrue(any(q["scope"] == "pessoa_informada" and "novo ciclo" in q["query"] for q in plan))
        self.assertTrue(any("WinCC" in q["query"] for q in plan))
        self.assertTrue(any(q["category"] == "internacional" for q in plan))
        self.assertTrue(all(len(q["query"]) < 600 for q in plan))

    def test_triage_does_not_use_query_as_company_evidence(self):
        items = {}
        abyss.ingest(items, [{"url": "https://other.example/1", "title": "Empresa diferente", "snippet": "Sem relação"}], '"Aché"', "compras", "test", [])
        result = discovery.assess_sources(items, "Aché")
        signals = next(iter(result.values()))["target_signals"]
        self.assertEqual(signals["names_in_title_or_snippet"], [])
        self.assertTrue(signals["review_required"])

    def test_provider_pagination_and_freshness_mapping(self):
        with patch.dict(os.environ, {"BRAVE_API_KEY": "fixture"}), patch("abyss.fetch_json", return_value={"web": {"results": []}}) as fetch:
            abyss.search("q", "brave", 10, page=3, freshness="month")
            params = parse_qs(urlsplit(fetch.call_args.args[0]).query)
            self.assertEqual(params["offset"], ["2"])
            self.assertEqual(params["freshness"], ["pm"])
            self.assertEqual(params["extra_snippets"], ["true"])
        with patch("abyss.fetch_json", return_value={"results": []}) as fetch:
            abyss.search("q", "searxng", 10, "http://localhost:8080", page=3, freshness="month")
            params = parse_qs(urlsplit(fetch.call_args.args[0]).query)
            self.assertEqual(params["pageno"], ["3"])
            self.assertEqual(params["time_range"], ["month"])

    def test_partial_searx_keeps_results_and_warning(self):
        data = {"results": [{"url": "https://example.com", "content": "Evidence"}], "unresponsive_engines": [["engine", "timeout"]]}
        with patch("abyss.fetch_json", return_value=data):
            result = abyss.search("q", "searxng", 10, "http://localhost:8080")
        self.assertEqual(len(result), 1)
        self.assertTrue(result.warnings)

    def test_budget_resume_and_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp, patch("abyss_engine.time.sleep"), contextlib.redirect_stdout(io.StringIO()):
            first, second = Path(tmp) / "first", Path(tmp) / "second"
            counter = iter(range(100))
            def results(*args, **kw):
                return [{"url": f"https://example.com/{next(counter)}", "title": "Empresa"}]
            with patch("abyss.search", side_effect=results) as search:
                code = abyss.main(["--company", "Empresa", "--provider", "searxng", "--searxng-url", "http://localhost:8080", "--pages", "2", "--max-queries", "2", "--max-requests", "2", "--output", str(first)])
                self.assertEqual(code, 0)
                self.assertEqual(search.call_count, 2)
            state = json.loads((first / "checkpoint.json").read_text())
            self.assertEqual([q["page"] for q in state["queries"]], [1, 2])
            with patch("abyss.search", side_effect=results) as search:
                self.assertEqual(abyss.main(["--resume", str(first / "checkpoint.json"), "--searxng-url", "http://localhost:8080", "--max-queries", "2", "--output", str(second)]), 0)
                self.assertEqual(search.call_count, 2)
            resumed = json.loads((second / "research.json").read_text())
            self.assertEqual(len(resumed["sources"]), 4)
            self.assertEqual(len(resumed["queries"]), 4)
            self.assertEqual(json.loads((first / "checkpoint.json").read_text()), state)

    def test_one_provider_failure_does_not_discard_other(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"BRAVE_API_KEY": "fixture"}), patch("abyss_engine.time.sleep"), contextlib.redirect_stdout(io.StringIO()):
            def results(query, provider, *args, **kwargs):
                if provider == "brave":
                    raise HTTPError("https://api.example", 429, "limited", {}, None)
                return [{"url": "https://example.com", "title": "Empresa"}]
            folder = Path(tmp) / "run"
            with patch("abyss.search", side_effect=results):
                code = abyss.main(["--company", "Empresa", "--provider", "both", "--searxng-url", "http://localhost:8080", "--max-queries", "2", "--output", str(folder)])
            state = json.loads((folder / "research.json").read_text())
            self.assertEqual(code, 2)
            self.assertEqual(len(state["sources"]), 1)
            self.assertEqual(len(state["queries"]), 3)


class UpdateTests(unittest.TestCase):
    def test_menu_reports_new_release_and_updates_only_on_choice(self):
        with patch("abyss_updates.check_update", return_value={"update_available": True, "latest": "v0.4.0", "url": "https://github.com/mister-m-1337/abyss/releases/tag/v0.4.0"}), patch("abyss_updates.apply_update", return_value={"updated": True}) as apply, patch("builtins.input", return_value="s"), contextlib.redirect_stdout(io.StringIO()) as output:
            terminal.updates_menu("0.3.0")
            apply.assert_called_once_with("0.3.0")
            self.assertIn("Encerre e reabra", output.getvalue())

    def test_git_timeout_has_controlled_error(self):
        with patch("abyss_updates.subprocess.run", side_effect=subprocess.TimeoutExpired("git", 60)):
            with self.assertRaisesRegex(ValueError, "tempo limite"):
                updates.git(Path("."), "fetch", "origin")

    def test_semver_comparison_not_lexicographic(self):
        self.assertGreater(updates.version_tuple("v0.10.0"), updates.version_tuple("0.9.0"))
        for bad in ["v1.0.0;touch /tmp/bad", "../main", "v1.0.0-beta"]:
            with self.assertRaises(ValueError):
                updates.version_tuple(bad)

    def test_cached_check_keeps_original_expiration(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache.json"
            checked = time.time() - 100
            cache.write_text(json.dumps({"checked_at": checked, "release": {"tag_name": "v0.10.0"}}))
            with patch("abyss_updates.urlopen") as network:
                result = updates.check_update("0.9.0", cache=cache)
                network.assert_not_called()
            self.assertTrue(result["update_available"])
            self.assertEqual(json.loads(cache.read_text())["checked_at"], checked)

    def test_dirty_install_blocks_before_fetch(self):
        info = {"update_available": True, "latest": "v0.4.0"}
        with tempfile.TemporaryDirectory() as tmp, patch("abyss_updates.check_update", return_value=info):
            def fake(repo, *args, **kwargs):
                return {("rev-parse", "--show-toplevel"): tmp, ("remote", "get-url", "origin"): "https://github.com/mister-m-1337/abyss.git", ("status", "--porcelain"): " M abyss.py"}[args]
            with patch("abyss_updates.git", side_effect=fake) as git:
                with self.assertRaisesRegex(ValueError, "alterações"):
                    updates.apply_update("0.3.0", Path(tmp))
                self.assertFalse(any(call.args[1] == "fetch" for call in git.call_args_list))

    def test_git_update_fast_forwards_and_preserves_ignored_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "install"
            upstream = Path(tmp) / "upstream"
            repo.mkdir(); upstream.mkdir()
            def cmd(path, *args):
                return subprocess.check_output(["git", "-C", str(path), *args], text=True, stderr=subprocess.DEVNULL).strip()
            cmd(upstream, "init", "-b", "main")
            cmd(upstream, "config", "user.name", "ABYSS test")
            cmd(upstream, "config", "user.email", "test@example.invalid")
            (upstream / ".gitignore").write_text("output/\n")
            (upstream / "version.txt").write_text("0.3.0")
            cmd(upstream, "add", "."); cmd(upstream, "commit", "-m", "initial")
            subprocess.check_call(["git", "clone", str(upstream), str(repo)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            cmd(repo, "remote", "set-url", "origin", "https://github.com/mister-m-1337/abyss.git")
            (repo / "output").mkdir(); (repo / "output" / "research.json").write_text("preserve")
            (upstream / "version.txt").write_text("0.4.0")
            cmd(upstream, "add", "."); cmd(upstream, "commit", "-m", "release"); cmd(upstream, "tag", "v0.4.0")
            original_git = updates.git
            def local_transport(path, *args, **kwargs):
                if args[0] == "fetch":
                    args = ("fetch", "--no-tags", str(upstream), args[-1])
                return original_git(path, *args, **kwargs)
            with patch("abyss_updates.check_update", return_value={"update_available": True, "latest": "v0.4.0"}), patch("abyss_updates.git", side_effect=local_transport):
                self.assertTrue(updates.apply_update("0.3.0", repo)["updated"])
            self.assertEqual((repo / "version.txt").read_text(), "0.4.0")
            self.assertEqual((repo / "output" / "research.json").read_text(), "preserve")
            self.assertEqual(cmd(repo, "status", "--porcelain"), "")


if __name__ == "__main__":
    unittest.main()
