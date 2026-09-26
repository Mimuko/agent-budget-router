"""Cursor / Codex adapter emit path: identical human summary, JSON-only stdout."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from human_summary import format_human_summary  # noqa: E402

CURSOR_ADAPTER = ROOT / "host-shims" / "cursor" / "cursor_adapter.py"
CODEX_ADAPTER = ROOT / "host-shims" / "codex" / "codex_adapter.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


cursor_adapter = _load("cursor_adapter_under_test", CURSOR_ADAPTER)
codex_adapter = _load("codex_adapter_under_test", CODEX_ADAPTER)


def case_b() -> dict:
    return {
        "schema_version": "skill-v1",
        "decision": "PREFLIGHT",
        "resolution_status": "RESOLVED",
        "state": "NEEDS_CONFIRMATION",
        "execution_policy": "CONFIRM_FIRST",
        "reason": "medium_task",
        "preflight": {
            "recommended_policy": "SPLIT",
            "task_class": "feature_build",
            "base_reason": "feature_build",
            "recommendation_reason": "budget_unavailable",
        },
        "forward": {"allowed": False},
    }


def _summary_tail(stderr: str) -> str:
    marker = "実行前チェック結果"
    index = stderr.rfind(marker)
    assert index >= 0, stderr
    return stderr[index:]


def _capture_emit(emit_fn, result: dict) -> tuple[int, str, str]:
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = emit_fn(result)
    return code, out.getvalue(), err.getvalue()


def _emit_subprocess(adapter_path: Path, result: dict) -> subprocess.CompletedProcess[bytes]:
    """Run adapter emit in a child process and return raw stdout/stderr bytes."""
    runner = (
        "import importlib.util, json, sys\n"
        f"path = r'{adapter_path}'\n"
        "spec = importlib.util.spec_from_file_location('adapter_emit', path)\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(module)\n"
        "raise SystemExit(module._emit_result(json.load(sys.stdin)))\n"
    )
    env = {
        key: value for key, value in os.environ.items()
        if key not in {"PYTHONIOENCODING", "PYTHONUTF8"}
    }
    return subprocess.run(
        [sys.executable, "-c", runner],
        input=json.dumps(result, ensure_ascii=True).encode("utf-8"),
        capture_output=True,
        check=False,
        env=env,
    )


def test_cursor_and_codex_emit_identical_summary_tail():
    fixture = case_b()
    expected = format_human_summary(fixture)
    cursor_code, cursor_out, cursor_err = _capture_emit(cursor_adapter._emit_result, fixture)
    codex_code, codex_out, codex_err = _capture_emit(codex_adapter._emit_result, fixture)

    assert cursor_code == 0
    assert codex_code == 0
    assert _summary_tail(cursor_err) == expected
    assert _summary_tail(codex_err) == expected
    assert _summary_tail(cursor_err) == _summary_tail(codex_err)
    assert json.loads(cursor_out) == fixture
    assert json.loads(codex_out) == fixture
    assert "human_summary" not in cursor_out
    assert cursor_err.rstrip().endswith(expected.rstrip())
    assert codex_err.rstrip().endswith(expected.rstrip())


def test_contract_violation_exits_2_without_summary_block():
    broken = {"schema_version": "skill-v1", "decision": "SKIP"}
    for emit_fn in (cursor_adapter._emit_result, codex_adapter._emit_result):
        code, out, err = _capture_emit(emit_fn, broken)
        assert code == 2
        assert "実行前チェック結果" not in err
        assert "contract violation:" in err
        assert json.loads(out) == broken


def test_null_forward_is_contract_violation_not_attribute_error():
    broken = {**case_b(), "forward": None}
    for emit_fn in (cursor_adapter._emit_result, codex_adapter._emit_result):
        code, out, err = _capture_emit(emit_fn, broken)
        assert code == 2
        assert "contract violation:" in err
        assert "forward.allowed" in err
        assert "実行前チェック結果" not in err
        assert json.loads(out) == broken


def test_subprocess_stderr_is_utf8_for_both_adapters():
    fixture = case_b()
    expected = format_human_summary(fixture)
    expected_marker = "実行前チェック結果".encode("utf-8")
    expected_policy = "推奨方針: 分割して進める".encode("utf-8")
    for adapter_path in (CURSOR_ADAPTER, CODEX_ADAPTER):
        completed = _emit_subprocess(adapter_path, fixture)
        assert completed.returncode == 0, completed.stderr
        # Decode as UTF-8; this fails if the adapter still wrote cp932.
        stderr_text = completed.stderr.decode("utf-8").replace("\r\n", "\n")
        assert "実行前チェック結果" in stderr_text
        assert expected_marker in completed.stderr
        assert expected_policy in completed.stderr
        assert stderr_text.rstrip().endswith(expected.rstrip())
        assert json.loads(completed.stdout.decode("utf-8")) == fixture
