"""Machine-readable projection of a Spec Kit Loop contract and evidence.

This built-in step intentionally reads the loop extension's durable files
rather than agent output. It projects state for workflows and read-only status
inspection; the workflow engine owns the pre-``running`` lease lifecycle.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
CRITERION_RE = re.compile(r"^\|\s*(D[A-Za-z0-9_-]+)\s*\|.*\|\s*([^|]+)\|\s*$")
MAX_ITERATIONS_RE = re.compile(r"^- Max iterations:\s*(\d+)\s*$", re.MULTILINE)
ITERATIONS_RE = re.compile(r"^- Iterations run:\s*(\d+)\s*$", re.MULTILINE)
BOOL_FIELDS = {
    "require_human_signoff": re.compile(
        r"^- Human sign-off required before done:\s*(true|false)\s*$",
        re.MULTILINE | re.IGNORECASE,
    ),
    "done_requires_checker_pass": re.compile(
        r"^- Checker-pass required before done:\s*(true|false)\s*$",
        re.MULTILINE | re.IGNORECASE,
    ),
    "block_done_on_open_debt": re.compile(
        r"^- Open blocking debt blocks done:\s*(true|false)\s*$",
        re.MULTILINE | re.IGNORECASE,
    ),
    "checker_independent": re.compile(
        r"^- Checker is independent:\s*(true|false)\s*$",
        re.MULTILINE | re.IGNORECASE,
    ),
    "checker_adversarial": re.compile(
        r"^- Checker is adversarial:\s*(true|false)\s*$",
        re.MULTILINE | re.IGNORECASE,
    ),
}


class LoopStateError(ValueError):
    """Raised when required durable state is absent or malformed."""


def validate_new_run_inputs(inputs: dict[str, Any]) -> None:
    """Reject values that the native workflow schema cannot express."""
    spec = inputs.get("spec")
    if not isinstance(spec, str) or not spec.strip():
        raise LoopStateError("Required input 'spec' must be a non-empty feature description.")
    integration = inputs.get("integration", "auto")
    if integration not in {"auto", "codex"}:
        raise LoopStateError("Input 'integration' must be one of: auto, codex.")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LoopStateError(f"Cannot read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise LoopStateError(f"Expected JSON object in {path}.")
    return data


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
    except OSError as exc:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise LoopStateError(f"Cannot write {path}: {exc}") from exc


def _feature_directory(project_root: Path) -> Path:
    feature_file = project_root / ".specify" / "feature.json"
    feature = _read_json(feature_file)
    raw_path = feature.get("feature_directory")
    if not isinstance(raw_path, str) or not raw_path:
        raise LoopStateError(".specify/feature.json has no feature_directory.")
    feature_dir = (project_root / raw_path).resolve()
    try:
        feature_dir.relative_to(project_root.resolve())
    except ValueError as exc:
        raise LoopStateError("feature_directory must remain inside the project root.") from exc
    return feature_dir


def _section(text: str, heading: str) -> str:
    pattern = re.compile(rf"^## {re.escape(heading)}\s*$([\s\S]*?)(?=^## |\Z)", re.MULTILINE)
    match = pattern.search(text)
    return "" if match is None else match.group(1)


def _parse_bool_fields(loop_text: str) -> dict[str, bool | None]:
    result: dict[str, bool | None] = {}
    for name, pattern in BOOL_FIELDS.items():
        match = pattern.search(loop_text)
        result[name] = None if match is None else match.group(1).lower() == "true"
    return result


def _parse_criteria(loop_text: str) -> dict[str, str]:
    criteria: dict[str, str] = {}
    for line in _section(loop_text, "Done-criteria").splitlines():
        match = CRITERION_RE.match(line)
        if match is not None:
            criteria[match.group(1)] = match.group(2).strip().lower()
    return criteria


def _blocking_debt(debt_text: str) -> list[str]:
    blocking: list[str] = []
    for line in _section(debt_text, "Open debt").splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 6 or cells[0] in {"ID", "---"}:
            continue
        severity, status = cells[4].lower(), cells[5].lower()
        if severity in {"high", "blocking"} and status in {"open", "pending"}:
            blocking.append(cells[0])
    return blocking


def _passed_verdicts(verdict_text: str) -> set[str]:
    passed: set[str] = set()
    for line in verdict_text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 7 or cells[0] in {"ID", "---"}:
            continue
        if cells[4].lower() == "pass" and cells[5].lower() in {"high", "medium"}:
            passed.add(cells[0])
    return passed


def _signoff_count(debt_text: str) -> int:
    count = 0
    for line in _section(debt_text, "Sign-off log").splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 4 and cells[0] not in {"Date", "---"}:
            count += 1
    return count


def _new_state(
    *,
    project_root: Path,
    run_id: str,
    variant: str,
    action: str,
    outcome: str,
    next_action: str,
    feature_dir: Path | None = None,
    loop_dir: Path | None = None,
    detail: str | None = None,
    criteria: dict[str, str] | None = None,
    policy: dict[str, bool | None] | None = None,
    blocking_debt: list[str] | None = None,
    iterations: dict[str, int | None] | None = None,
    signoff_count: int | None = None,
    review_decision: dict[str, Any] | None = None,
    operational_status: str = "external",
    current_step_id: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "variant": variant,
        "operational_status": operational_status,
        "current_step_id": current_step_id,
        "error": error,
        "outcome": outcome,
        "next_action": next_action,
        "feature_directory": (None if feature_dir is None else str(feature_dir.relative_to(project_root))),
        "loop_directory": None if loop_dir is None else str(loop_dir.relative_to(project_root)),
        "criteria": criteria or {},
        "policy": policy or {},
        "blocking_debt": blocking_debt or [],
        "iterations": iterations or {},
        "signoff_count": signoff_count or 0,
        "review_decision": review_decision,
        "detail": detail,
        "updated_at": timestamp,
        "stage_history": [
            {
                "action": action,
                "timestamp": timestamp,
                "detail": detail,
                "operational_status": operational_status,
                "current_step_id": current_step_id,
            }
        ],
    }


def _read_prior_state(state_path: Path) -> dict[str, Any] | None:
    """Return a prior sidecar state when one is already durable."""
    return _read_json(state_path) if state_path.exists() else None


def _preserve_lifecycle_fields(state: dict[str, Any], prior: dict[str, Any] | None) -> dict[str, Any]:
    """Keep engine-derived state when an explicit adapter action recomputes outcome."""
    if prior is None:
        return state
    for field in ("operational_status", "current_step_id", "error"):
        if field in prior:
            state[field] = prior[field]
    history = prior.get("stage_history")
    if isinstance(history, list):
        state["stage_history"] = [*history, *state["stage_history"]]
    return state


def _lifecycle_projection(native: dict[str, Any], prior: dict[str, Any] | None) -> tuple[str, str, str]:
    """Map native run states to an inspectable loop outcome and next action."""
    status = native.get("status")
    current_step = native.get("current_step_id")
    if status == "completed":
        return "completed", "none", "Workflow engine completed all stages."
    if status == "aborted":
        return "aborted", "none", "Workflow was aborted by a gate decision."
    if status == "failed":
        return "failed", "remediate", "Workflow failed; record remediation before retrying the failed stage."
    if status == "paused":
        return "paused", "resume", f"Workflow is paused at {current_step or 'an unspecified stage'}."
    if status == "running" and prior is not None:
        prior_outcome = prior.get("outcome")
        if prior_outcome in {"paused", "failed", "aborted"}:
            return (
                "pending",
                str(current_step or "workflow"),
                "Workflow resumed and is executing its current stage.",
            )
    if prior is not None:
        outcome = prior.get("outcome")
        next_action = prior.get("next_action")
        if isinstance(outcome, str) and isinstance(next_action, str):
            return outcome, next_action, "Workflow is running."
    return "pending", "define-loop", "Workflow started; loop contract is not yet defined."


def sync_lifecycle_state(
    project_root: Path,
    native: dict[str, Any],
    *,
    variant: str,
) -> dict[str, Any]:
    """Project one atomically persisted native state into the loop sidecar.

    This function is invoked by the engine's opt-in state observer after each
    ``state.json`` write. It does not modify native workflow state, so a
    competing resumer rejected before a native write cannot alter the sidecar.
    """
    run_id = native.get("run_id")
    if not isinstance(run_id, str) or not RUN_ID_RE.fullmatch(run_id):
        raise LoopStateError("Workflow run ID is invalid.")
    if variant not in {"governed", "yolo"}:
        raise LoopStateError("Variant must be governed or yolo.")
    status = native.get("status")
    if status not in {"created", "running", "paused", "failed", "completed", "aborted"}:
        raise LoopStateError("Native workflow status is invalid.")

    state_path = project_root / ".specify" / "workflows" / "runs" / run_id / "loop-state.json"
    prior = _read_prior_state(state_path)
    outcome, next_action, detail = _lifecycle_projection(native, prior)
    timestamp = datetime.now(timezone.utc).isoformat()
    if prior is None:
        try:
            feature_dir = _feature_directory(project_root)
        except LoopStateError:
            feature_dir = None
        state = _new_state(
            project_root=project_root,
            run_id=run_id,
            variant=variant,
            action="native-state",
            outcome=outcome,
            next_action=next_action,
            feature_dir=feature_dir,
            loop_dir=None if feature_dir is None else feature_dir / "loop",
            detail=detail,
            operational_status=status,
            current_step_id=native.get("current_step_id"),
            error=native.get("error"),
        )
    else:
        state = dict(prior)
        state.update(
            {
                "variant": variant,
                "operational_status": status,
                "current_step_id": native.get("current_step_id"),
                "error": native.get("error"),
                "outcome": outcome,
                "next_action": next_action,
                "detail": detail,
                "updated_at": timestamp,
            }
        )
        history = prior.get("stage_history")
        state["stage_history"] = list(history) if isinstance(history, list) else []
        state["stage_history"].append(
            {
                "action": "native-state",
                "source": "workflow-engine",
                "timestamp": timestamp,
                "operational_status": status,
                "current_step_id": native.get("current_step_id"),
                "detail": detail,
            }
        )
    _atomic_write_json(state_path, state)
    return state


def sync_loop_state(
    project_root: Path,
    run_id: str,
    *,
    variant: str,
    action: str,
    completion_verdict: Any = "",
) -> dict[str, Any]:
    """Write and return the adapter's durable workflow outcome projection."""
    if not RUN_ID_RE.fullmatch(run_id):
        raise LoopStateError("Workflow run ID is invalid.")
    if variant not in {"governed", "yolo"}:
        raise LoopStateError("Variant must be governed or yolo.")
    if action not in {"initialize", "evaluate", "record-signoff", "enforce"}:
        raise LoopStateError("Unsupported loop-state synchronization action.")

    run_dir = project_root / ".specify" / "workflows" / "runs" / run_id
    state_path = run_dir / "loop-state.json"
    prior = _read_prior_state(state_path)
    if action == "initialize":
        feature_dir = _feature_directory(project_root)
        state = _new_state(
            project_root=project_root,
            run_id=run_id,
            variant=variant,
            action=action,
            outcome="pending",
            next_action="define-loop",
            feature_dir=feature_dir,
            loop_dir=feature_dir / "loop",
            detail="Awaiting a defined loop contract.",
        )
        state = _preserve_lifecycle_fields(state, prior)
        _atomic_write_json(state_path, state)
        return state

    feature_dir = _feature_directory(project_root)
    loop_dir = feature_dir / "loop"
    loop_path = loop_dir / "loop.md"
    debt_path = loop_dir / "debt.md"
    verdict_path = loop_dir / "verdicts.md"
    if not loop_path.is_file() or not debt_path.is_file() or not verdict_path.is_file():
        state = _new_state(
            project_root=project_root,
            run_id=run_id,
            variant=variant,
            action=action,
            outcome="incomplete",
            next_action="define-loop",
            feature_dir=feature_dir,
            loop_dir=loop_dir,
            detail="A loop contract, checker verdict ledger, and debt ledger are required.",
        )
        state = _preserve_lifecycle_fields(state, prior)
        _atomic_write_json(state_path, state)
        return state

    loop_text = loop_path.read_text(encoding="utf-8")
    debt_text = debt_path.read_text(encoding="utf-8")
    verdict_text = verdict_path.read_text(encoding="utf-8")
    criteria = _parse_criteria(loop_text)
    policy = _parse_bool_fields(loop_text)
    blocking_debt = _blocking_debt(debt_text)
    max_iterations_match = MAX_ITERATIONS_RE.search(loop_text)
    iterations_match = ITERATIONS_RE.search(loop_text)
    iterations = {
        "current": None if iterations_match is None else int(iterations_match.group(1)),
        "maximum": None if max_iterations_match is None else int(max_iterations_match.group(1)),
    }
    signoff_count = _signoff_count(debt_text)

    expected_signoff = variant == "governed"
    policy_valid = (
        policy["require_human_signoff"] is expected_signoff
        and policy["done_requires_checker_pass"] is True
        and policy["block_done_on_open_debt"] is True
        and policy["checker_independent"] is True
        and policy["checker_adversarial"] is True
    )
    passed_verdicts = _passed_verdicts(verdict_text)
    all_pass = bool(criteria) and all(
        status == "checker-pass" and criterion_id in passed_verdicts for criterion_id, status in criteria.items()
    )
    exhausted = (
        iterations["current"] is not None
        and iterations["maximum"] is not None
        and iterations["current"] >= iterations["maximum"]
        and not all_pass
    )

    if not policy_valid:
        outcome, next_action, detail = (
            "incompatible",
            "repair-loop-policy",
            "Loop policy does not match the selected workflow variant.",
        )
    elif not criteria:
        outcome, next_action, detail = "incomplete", "define-loop", "No checkable done criteria were recorded."
    elif exhausted:
        outcome, next_action, detail = "incomplete", "human-review", "The hard iteration ceiling was exhausted."
    elif not all_pass:
        outcome, next_action, detail = "incomplete", "maker", "At least one criterion lacks checker-pass evidence."
    elif blocking_debt:
        outcome, next_action, detail = (
            "incomplete",
            "resolve-blocking-debt",
            "Blocking comprehension debt remains open.",
        )
    elif variant == "governed" and action not in {"record-signoff"}:
        outcome, next_action, detail = (
            "pending",
            "completion-signoff",
            "Independent evidence passes; human sign-off is required.",
        )
    elif variant == "governed" and completion_verdict != "approve":
        outcome, next_action, detail = "incomplete", "completion-signoff", "A governed completion approval is required."
    else:
        outcome, next_action, detail = "completed", "none", "All deterministic completion conditions are satisfied."

    review_decision = None
    if action == "record-signoff":
        review_decision = {
            "stage": "completion",
            "verdict": completion_verdict,
            "source": "workflow input",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": run_id,
        }

    state = _new_state(
        project_root=project_root,
        run_id=run_id,
        variant=variant,
        action=action,
        outcome=outcome,
        next_action=next_action,
        feature_dir=feature_dir,
        loop_dir=loop_dir,
        detail=detail,
        criteria=criteria,
        policy=policy,
        blocking_debt=blocking_debt,
        iterations=iterations,
        signoff_count=signoff_count,
        review_decision=review_decision,
    )
    state = _preserve_lifecycle_fields(state, prior)
    _atomic_write_json(state_path, state)
    return state


def status_payload(project_root: Path, run_id: str) -> dict[str, Any]:
    """Merge native operational state with the adapter's business outcome."""
    if not RUN_ID_RE.fullmatch(run_id):
        raise LoopStateError("Workflow run ID is invalid.")
    run_dir = project_root / ".specify" / "workflows" / "runs" / run_id
    native = _read_json(run_dir / "state.json")
    adapter = _read_json(run_dir / "loop-state.json")
    return {
        "run_id": run_id,
        "operational_status": native.get("status"),
        "current_step_id": native.get("current_step_id"),
        "error": native.get("error"),
        "outcome": adapter.get("outcome"),
        "next_action": adapter.get("next_action"),
        "stage_history": adapter.get("stage_history", []),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read a Spec Kit loop workflow outcome.")
    parser.add_argument("--status", metavar="RUN_ID", required=True)
    parser.add_argument("--project-root", default=".")
    args = parser.parse_args()
    try:
        payload = status_payload(Path(args.project_root).resolve(), args.status)
    except LoopStateError as exc:
        parser.error(str(exc))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
