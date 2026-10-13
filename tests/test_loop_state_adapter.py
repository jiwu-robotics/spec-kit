"""Consumer behavior for the bundled loop workflow state adapter."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from specify_cli.workflows.steps.loop_state.state_adapter import (
    sync_lifecycle_state,
    sync_loop_state,
)


ROOT = Path(__file__).resolve().parent.parent


def _write_feature_project(
    root: Path,
    *,
    feature_directory: str = "specs/001-feature",
    state_directory: str | None = None,
) -> Path:
    specify_dir = root / ".specify"
    specify_dir.mkdir(parents=True, exist_ok=True)
    (specify_dir / "feature.json").write_text(
        json.dumps({"feature_directory": feature_directory}), encoding="utf-8"
    )
    feature_dir = (root / feature_directory).resolve()
    feature_dir.mkdir(parents=True, exist_ok=True)
    if state_directory is not None:
        _write_loop_config(root, state_directory)
    return feature_dir


def _write_loop_config(root: Path, state_directory: str) -> None:
    config_path = root / ".specify" / "extensions" / "loop" / "loop-config.yml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        yaml.safe_dump({"state": {"directory": state_directory}}), encoding="utf-8"
    )


def _write_loop_files(
    loop_dir: Path,
    *,
    human_signoff: bool,
    checker_pass: bool = True,
    blocking_debt: bool = False,
) -> None:
    loop_dir.mkdir(parents=True, exist_ok=True)
    (loop_dir / "loop.md").write_text(
        "# Loop Contract\n\n"
        "## Done-criteria\n"
        "| ID | Criterion | Verification | Status |\n"
        "|----|-----------|--------------|--------|\n"
        "| D1 | Implement feature | Run verification | checker-pass |\n\n"
        "## Budget\n"
        "- Max iterations: 8\n"
        "- Iterations run: 1\n\n"
        "## Guardrails\n"
        f"- Human sign-off required before done: {str(human_signoff).lower()}\n"
        "- Checker-pass required before done: true\n"
        "- Checker is independent: true\n"
        "- Checker is adversarial: true\n"
        "- Open blocking debt blocks done: true\n",
        encoding="utf-8",
    )
    debt_rows = (
        "| B1 | implementation | Not understood | code | high | open |\n"
        if blocking_debt
        else ""
    )
    (loop_dir / "debt.md").write_text(
        "# Comprehension Debt\n\n"
        "## Open debt\n"
        "| ID | Scope | Description | Category | Severity | Status |\n"
        "|----|-------|-------------|----------|----------|--------|\n"
        f"{debt_rows}\n"
        "## Sign-off log\n"
        "|---|---|---|---|" + chr(10),
        encoding="utf-8",
    )
    verdict = "pass" if checker_pass else "fail"
    (loop_dir / "verdicts.md").write_text(
        "# Checker Verdicts\n\n"
        "| ID | Iteration | Criterion | Method | Verdict | Confidence | Date |\n"
        "|----|-----------|-----------|--------|---------|------------|------|\n"
        f"| D1 | 1 | Implement feature | verification | {verdict} | high | 2026-01-01 |\n",
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("checker_pass", "blocking_debt", "expected_outcome", "expected_action"),
    [
        (False, False, "incomplete", "maker"),
        (True, True, "incomplete", "resolve-blocking-debt"),
        (True, False, "completed", "none"),
    ],
)
def test_yolo_evaluation_requires_checker_pass_and_no_blocking_debt(
    tmp_path: Path,
    checker_pass: bool,
    blocking_debt: bool,
    expected_outcome: str,
    expected_action: str,
) -> None:
    feature_dir = _write_feature_project(tmp_path)
    initialized = sync_loop_state(
        tmp_path, "yolo-check", variant="yolo", action="initialize"
    )
    loop_dir = tmp_path / initialized["loop_directory"]
    _write_loop_files(
        loop_dir,
        human_signoff=False,
        checker_pass=checker_pass,
        blocking_debt=blocking_debt,
    )

    result = sync_loop_state(
        tmp_path, "yolo-check", variant="yolo", action="evaluate"
    )

    assert result["outcome"] == expected_outcome
    assert result["next_action"] == expected_action
    assert result["loop_directory"] == str(loop_dir.relative_to(tmp_path))
    assert result["policy"]["require_human_signoff"] is False
    assert result["policy"]["done_requires_checker_pass"] is True
    assert result["policy"]["block_done_on_open_debt"] is True
    assert result["signoff_count"] == 0
    assert feature_dir / "loop" == loop_dir


@pytest.mark.parametrize(
    ("state_directory", "expected_relative_directory"),
    [(None, "loop"), ("adapter-state/nested", "adapter-state/nested")],
)
def test_initialize_and_evaluate_share_default_or_configured_state_directory(
    tmp_path: Path,
    state_directory: str | None,
    expected_relative_directory: str,
) -> None:
    feature_dir = _write_feature_project(tmp_path, state_directory=state_directory)
    initialized = sync_loop_state(
        tmp_path, "directory-check", variant="yolo", action="initialize"
    )
    expected_dir = feature_dir / expected_relative_directory
    assert initialized["loop_directory"] == str(
        expected_dir.relative_to(tmp_path)
    )
    _write_loop_files(expected_dir, human_signoff=False)

    if state_directory is not None:
        # A run keeps evaluating the directory selected during initialization.
        _write_loop_config(tmp_path, "changed-after-initialize")

    evaluated = sync_loop_state(
        tmp_path, "directory-check", variant="yolo", action="evaluate"
    )

    assert evaluated["outcome"] == "completed"
    assert evaluated["loop_directory"] == initialized["loop_directory"]
    assert (expected_dir / "loop.md").is_file()


def test_lifecycle_projection_persists_configured_loop_directory(
    tmp_path: Path,
) -> None:
    feature_dir = _write_feature_project(
        tmp_path, state_directory="runtime-loop-state"
    )

    state = sync_lifecycle_state(
        tmp_path,
        {"run_id": "observer-path", "status": "created"},
        variant="yolo",
    )

    assert state["feature_directory"] == str(feature_dir.relative_to(tmp_path))
    assert state["loop_directory"] == "specs/001-feature/runtime-loop-state"


def test_relative_default_project_root_handles_absolute_feature_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    feature_dir = tmp_path / "specs" / "absolute-feature"
    _write_feature_project(Path("."), feature_directory=str(feature_dir))
    lifecycle_state = sync_lifecycle_state(
        Path("."),
        {"run_id": "relative-root-observer", "status": "created"},
        variant="yolo",
    )
    assert lifecycle_state["feature_directory"] == "specs/absolute-feature"
    assert lifecycle_state["loop_directory"] == "specs/absolute-feature/loop"

    initialized = sync_loop_state(
        Path("."), "relative-root", variant="yolo", action="initialize"
    )
    expected_dir = feature_dir / "loop"
    _write_loop_files(expected_dir, human_signoff=False)
    evaluated = sync_loop_state(
        Path("."), "relative-root", variant="yolo", action="evaluate"
    )

    assert initialized["feature_directory"] == "specs/absolute-feature"
    assert evaluated["outcome"] == "completed"
    assert evaluated["loop_directory"] == "specs/absolute-feature/loop"


def test_installed_loop_state_module_reports_status_from_project_files(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / ".specify" / "workflows" / "runs" / "installed-module"
    run_dir.mkdir(parents=True)
    (run_dir / "state.json").write_text(
        json.dumps(
            {
                "run_id": "installed-module",
                "status": "paused",
                "current_step_id": "review",
                "error": None,
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "loop-state.json").write_text(
        json.dumps(
            {
                "outcome": "pending",
                "next_action": "spec-approval",
                "stage_history": [],
            }
        ),
        encoding="utf-8",
    )
    source_path = str(ROOT / "src")
    existing_pythonpath = os.environ.get("PYTHONPATH")
    env = {
        **os.environ,
        "PYTHONPATH": (
            source_path
            if not existing_pythonpath
            else source_path + os.pathsep + existing_pythonpath
        ),
    }
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "specify_cli.workflows.steps.loop_state.state_adapter",
            "--status",
            "installed-module",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert not result.stderr
    payload = json.loads(result.stdout)
    assert payload["operational_status"] == "paused"
    assert payload["outcome"] == "pending"
    assert payload["next_action"] == "spec-approval"
