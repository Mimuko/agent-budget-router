"""Tests for scan_workspace.py"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from scan_workspace import (  # noqa: E402
    extract_task_keywords,
    ignored_by_gitignore,
    relevance_score,
    scan_workspace,
)


def test_extract_task_keywords():
    task = "Add validation to docs-sheets-sync manifest in mimu-core/skills/"
    kws = extract_task_keywords(task)
    assert "docs-sheets-sync" in kws or any("docs-sheets" in k for k in kws)


def test_gitignore_fnmatch():
    assert ignored_by_gitignore("node_modules/pkg/index.js", ["node_modules/"])
    assert ignored_by_gitignore("foo.pyc", ["*.pyc"])


def test_scan_with_hint_limits_files():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "src").mkdir()
        (root / "src" / "target.py").write_text("x = 1\n" * 10, encoding="utf-8")
        (root / "src" / "other.py").write_text("y = 2\n" * 100, encoding="utf-8")
        result = scan_workspace(root, hints=["src/target.py"])
        paths = [c["path"] for c in result["candidate_files"]]
        assert "src/target.py" in paths
        assert "src/other.py" not in paths


def test_relevance_score_prefers_hints():
    assert relevance_score("mimu-core/skills/docs-sheets-sync/SKILL.md", ["docs-sheets-sync"], []) >= 6
