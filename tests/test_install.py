"""User-scope distribution lifecycle and isolation checks."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PACKAGE = Path(__file__).resolve().parents[1]
INSTALLER = PACKAGE / "install.py"


class InstallTests(unittest.TestCase):
    def run_install(self, home: Path, action: str, success: bool = True):
        result = subprocess.run(
            [sys.executable, str(INSTALLER), action, "--home", str(home)],
            capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(result.returncode == 0, success, result.stderr)
        return result

    def test_lifecycle_and_cross_workspace_adapters(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            workspace = home / "other-workspace"
            workspace.mkdir()
            self.run_install(home, "install")
            for host, adapter in (("cursor", "cursor_adapter.py"), ("codex", "codex_adapter.py")):
                root = home / (".cursor" if host == "cursor" else ".agents") / "skills" / "agent-budget-router"
                result = subprocess.run(
                    [sys.executable, str(root / "scripts" / adapter), "--task", "Fix typo in README"],
                    cwd=workspace, capture_output=True, text=True, encoding="utf-8",
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('"state": "READY"', result.stdout)
            self.run_install(home, "update")
            self.run_install(home, "rollback")
            self.assertTrue((home / ".agents" / "skills" / "agent-budget-router" / "SKILL.md").exists())
            self.run_install(home, "uninstall")
            self.assertFalse((home / ".cursor" / "skills" / "agent-budget-router").exists())
            self.run_install(home, "rollback")
            self.assertTrue((home / ".cursor" / "skills" / "agent-budget-router" / "SKILL.md").exists())

    def test_refuses_unmanaged_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            target = home / ".cursor" / "skills" / "agent-budget-router"
            target.mkdir(parents=True)
            (target / "SKILL.md").write_text("personal skill", encoding="utf-8")
            self.run_install(home, "install", success=False)
            self.assertEqual((target / "SKILL.md").read_text(encoding="utf-8"), "personal skill")
            self.assertFalse((home / ".agents" / "skills" / "agent-budget-router").exists())


if __name__ == "__main__":
    unittest.main()
