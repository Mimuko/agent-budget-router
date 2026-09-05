#!/usr/bin/env python3
"""Estimate candidate relevant files for agent context (not full repo scan)."""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
from pathlib import Path

TOKENS_PER_LINE = 15
MAX_CANDIDATE_FILES = 40
MAX_FILE_BYTES = 500_000

SECRET_PATTERNS = [
    r"\.env",
    r"credentials",
    r"secret",
    r"\.pem$",
    r"id_rsa",
    r"\.key$",
]

SKIP_DIRS = {
    ".git",
    "node_modules",
    "dist",
    "build",
    ".next",
    "__pycache__",
    ".venv",
    "venv",
    ".cursor",
    "coverage",
}

DEFAULT_EXTENSIONS = [
    ".py", ".ts", ".tsx", ".js", ".jsx", ".css", ".md",
    ".yaml", ".yml", ".json", ".html", ".go", ".rs", ".mdc",
]


def is_secret(path: Path) -> bool:
    s = str(path).replace("\\", "/").lower()
    return any(re.search(p, s) for p in SECRET_PATTERNS)


def load_gitignore_patterns(root: Path) -> list[str]:
    patterns: list[str] = []
    gi = root / ".gitignore"
    if gi.exists():
        for line in gi.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                patterns.append(line)
    return patterns


def ignored_by_gitignore(rel: str, patterns: list[str]) -> bool:
    name = Path(rel).name
    for pat in patterns:
        p = pat.rstrip("/")
        if pat.endswith("/"):
            if rel.startswith(p + "/") or rel == p or f"/{p}/" in f"/{rel}/":
                return True
            continue
        if fnmatch.fnmatch(name, p) or fnmatch.fnmatch(rel, p):
            return True
        if rel == p or rel.startswith(p + "/"):
            return True
    return False


def extract_task_keywords(task: str) -> list[str]:
    """Pull path-like tokens and module names from a task description."""
    keywords: set[str] = set()
    for m in re.findall(r"[`'\"]?([\w./\\-]+\.(?:py|ts|tsx|js|jsx|css|md|yaml|yml|json|mdc))[`'\"]?", task):
        keywords.add(m.replace("\\", "/").lower())
    for m in re.findall(r"[`'\"]?([\w][\w./\\-]{2,})[`'\"]?", task):
        token = m.replace("\\", "/").lower().strip("./")
        if "/" in token or token.endswith(("-sync", "-router", "-policy")):
            keywords.add(token)
    for word in re.findall(r"\b[a-z][a-z0-9-]{3,}\b", task.lower()):
        if word not in {"with", "from", "that", "this", "before", "after", "implement", "add"}:
            keywords.add(word)
    return sorted(keywords)


def relevance_score(rel: str, hints: list[str], keywords: list[str]) -> int:
    s = rel.replace("\\", "/").lower()
    score = 0
    for hint in hints:
        h = hint.replace("\\", "/").lower().strip()
        if not h:
            continue
        if s == h or s.endswith("/" + h) or h in s:
            score += 10
        elif Path(h).name.lower() in s:
            score += 6
    for kw in keywords:
        if kw in s or Path(kw).name in s:
            score += 4
        elif any(part == kw for part in s.split("/")):
            score += 2
    return score


def match_hints(path: Path, hints: list[str]) -> bool:
    return relevance_score(str(path).replace("\\", "/"), hints, []) > 0


def count_lines(path: Path) -> int:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return MAX_FILE_BYTES // 40
        return sum(1 for _ in path.open(encoding="utf-8", errors="ignore"))
    except OSError:
        return 0


def collect_by_glob(root: Path, globs: list[str]) -> list[Path]:
    found: list[Path] = []
    for pattern in globs:
        pattern = pattern.replace("\\", "/")
        found.extend(root.glob(pattern))
    return [p for p in found if p.is_file()]


def scan_workspace(
    root: Path,
    hints: list[str] | None = None,
    globs: list[str] | None = None,
    task: str | None = None,
    extensions: list[str] | None = None,
    min_relevance: int = 0,
) -> dict:
    hints = hints or []
    globs = globs or []
    extensions = extensions or DEFAULT_EXTENSIONS
    keywords = extract_task_keywords(task) if task else []
    gitignore = load_gitignore_patterns(root)
    seen: set[str] = set()
    candidates: list[dict] = []

    def consider(path: Path, forced: bool = False) -> None:
        if not path.is_file():
            return
        rel = str(path.relative_to(root)).replace("\\", "/")
        if rel in seen:
            return
        if any(part in SKIP_DIRS for part in path.parts):
            return
        if is_secret(path):
            return
        if ignored_by_gitignore(rel, gitignore):
            return
        if path.suffix.lower() not in extensions:
            return
        score = relevance_score(rel, hints, keywords)
        if not forced and hints and score == 0:
            return
        if not forced and not hints and keywords and score < min_relevance:
            return
        seen.add(rel)
        lines = count_lines(path)
        candidates.append(
            {
                "path": rel,
                "lines": lines,
                "estimated_tokens": lines * TOKENS_PER_LINE,
                "relevance_score": score,
            }
        )

    for path in collect_by_glob(root, globs):
        consider(path, forced=True)

    for path in root.rglob("*"):
        consider(path)

    candidates.sort(key=lambda c: (c["relevance_score"], c["estimated_tokens"]), reverse=True)
    candidates = candidates[:MAX_CANDIDATE_FILES]

    total_min = sum(c["estimated_tokens"] for c in candidates) if candidates else 0
    total_max = int(total_min * 1.3) if candidates else 0
    high_relevance = sum(1 for c in candidates if c["relevance_score"] >= 6)

    return {
        "root": str(root),
        "candidate_files": candidates,
        "file_count": len(candidates),
        "high_relevance_count": high_relevance,
        "task_keywords": keywords,
        "estimated_tokens": {"min": total_min, "max": total_max},
        "note": "Candidate relevant files only - not full repository size",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan workspace for relevant file candidates")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Workspace root")
    parser.add_argument("--hint", action="append", dest="hints", default=[], help="Path hint")
    parser.add_argument("--glob", action="append", dest="globs", default=[], help="Glob pattern")
    parser.add_argument("--task", help="Task description for keyword relevance")
    parser.add_argument("--min-relevance", type=int, default=2, help="Min score when using --task")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args(argv)

    result = scan_workspace(
        args.root.resolve(),
        hints=args.hints or None,
        globs=args.globs or None,
        task=args.task,
        min_relevance=args.min_relevance,
    )
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Root: {result['root']}")
        print(f"Candidates: {result['file_count']} (high relevance: {result['high_relevance_count']})")
        if result["task_keywords"]:
            print(f"Keywords: {', '.join(result['task_keywords'][:8])}")
        tok = result["estimated_tokens"]
        print(f"Estimated tokens: {tok['min']} - {tok['max']}")
        for c in result["candidate_files"][:10]:
            print(f"  [{c['relevance_score']}] {c['path']} ({c['lines']} lines)")
        if result["file_count"] > 10:
            print(f"  ... and {result['file_count'] - 10} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
