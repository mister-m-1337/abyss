import contextlib
import hashlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import abyss_config as config
import abyss_installer as installer


class InstallerTests(unittest.TestCase):
    def test_assets_for_supported_platforms(self):
        self.assertEqual(installer.platform_asset("Windows", "AMD64"), "ABYSS-Setup-windows-x64.exe")
        self.assertEqual(installer.platform_asset("Darwin", "arm64"), "ABYSS-Setup-macos-arm64")
        self.assertEqual(installer.platform_asset("Darwin", "x86_64"), "ABYSS-Setup-macos-x64")
        self.assertEqual(installer.platform_asset("Linux", "x86_64"), "ABYSS-Setup-linux-x64")
        with self.assertRaises(ValueError):
            installer.platform_asset("Linux", "arm64")

    def test_installation_preserves_research_and_reinstall_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, binary = Path(tmp) / "ABYSS install", Path(tmp) / "installer"
            binary.write_bytes(b"packaged executable fixture")
            result = installer.install_binary(binary, "0.4.0", root)
            research = root / "output" / "private.json"
            research.write_text("preserve")
            again = installer.install_binary(binary, "0.4.0", root)
            self.assertEqual(result["executable"], again["executable"])
            self.assertEqual(research.read_text(), "preserve")
            self.assertEqual(installer.installed_root(result["executable"]), root.resolve())
            self.assertTrue(Path(result["launcher"]).is_file())
            binary.write_bytes(b"different binary")
            with self.assertRaises(ValueError):
                installer.install_binary(binary, "0.4.0", root)

    def test_launcher_quotes_space_and_shell_characters(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "ABYSS ' $ HOME"
            root.mkdir()
            binary = root / "versions" / "v0.4.0" / "ABYSS"
            launcher, _ = installer.write_launchers(root, binary)
            text = launcher.read_text()
            self.assertIn("--ui", text)
            if os.name != "nt":
                import shlex
                self.assertEqual(shlex.split(text.splitlines()[2])[1], str(binary))

    def test_session_key_is_not_persisted(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True), patch("builtins.input", return_value="1"), patch("abyss_config.getpass.getpass", return_value="SECRET_FIXTURE"), contextlib.redirect_stdout(io.StringIO()) as output:
            config.configure(root=Path(tmp))
            saved = (Path(tmp) / "config.json").read_text()
            self.assertNotIn("SECRET_FIXTURE", saved)
            self.assertNotIn("SECRET_FIXTURE", output.getvalue())
            self.assertEqual(os.environ["BRAVE_API_KEY"], "SECRET_FIXTURE")

    def test_searx_rejects_credentials_and_saves_public_endpoint(self):
        with tempfile.TemporaryDirectory() as tmp, patch("builtins.input", side_effect=["2", "https://user:password@example.com"]), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(ValueError):
                config.configure(root=Path(tmp))
            self.assertFalse((Path(tmp) / "config.json").exists())
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True), patch("builtins.input", side_effect=["2", "http://localhost:8080"]), contextlib.redirect_stdout(io.StringIO()):
            settings = config.configure(root=Path(tmp))
            self.assertEqual(settings["searxng_url"], "http://localhost:8080")

    def test_binary_update_uses_checksum_and_keeps_old_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "old-installer"
            binary.write_bytes(b"old")
            root = Path(tmp) / "install"
            installed = installer.install_binary(binary, "0.3.0", root)
            research = root / "output" / "research.json"
            research.write_text("preserve")
            new = b"new executable fixture"
            def download(url, target, limit):
                target.write_bytes(hashlib.sha256(new).hexdigest().encode() if url.endswith(".sha256") else new)
            with patch("abyss_updates.check_update", return_value={"update_available": True, "latest": "v0.4.0"}), patch("abyss_installer.download", side_effect=download), patch("abyss_installer.platform_asset", return_value="ABYSS-Setup-linux-x64"):
                result = installer.update_binary("0.3.0", installed["executable"])
            self.assertTrue(result["updated"])
            self.assertEqual(Path(result["executable"]).read_bytes(), new)
            self.assertEqual(Path(installed["executable"]).read_bytes(), b"old")
            self.assertEqual(research.read_text(), "preserve")

    def test_checksum_mismatch_prevents_installation(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "old-installer"
            binary.write_bytes(b"old")
            old = installer.install_binary(binary, "0.3.0", Path(tmp) / "install")
            def download(url, target, limit):
                target.write_bytes(b"0" * 64 if url.endswith(".sha256") else b"tampered")
            with patch("abyss_updates.check_update", return_value={"update_available": True, "latest": "v0.4.0"}), patch("abyss_installer.download", side_effect=download), patch("abyss_installer.platform_asset", return_value="ABYSS-Setup-linux-x64"):
                with self.assertRaisesRegex(ValueError, "Checksum"):
                    installer.update_binary("0.3.0", old["executable"])
            self.assertEqual(json.loads((Path(old["root"]) / "installation.json").read_text())["version"], "v0.3.0")


if __name__ == "__main__":
    unittest.main()
