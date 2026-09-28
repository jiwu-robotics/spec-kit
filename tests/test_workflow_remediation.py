"""Workflow-engine coverage for failed-stage recovery notes."""

from __future__ import annotations

import pytest


def test_failed_workflow_requires_and_persists_remediation_note(tmp_path):
    from specify_cli.workflows.base import RunStatus
    from specify_cli.workflows.engine import RunState, WorkflowEngine

    state = RunState(run_id="failed-run", workflow_id="remediation-wf", project_root=tmp_path)
    state.status = RunStatus.FAILED
    state.current_step_index = 0
    state.current_step_id = "failed-step"
    state.error = "recorded failure"
    state.inputs = {"remediation_note": ""}
    state.save()
    (state.runs_dir / "workflow.yml").write_text(
        """
schema_version: "1.0"
workflow:
  id: "remediation-wf"
  name: "Remediation workflow"
  version: "1.0.0"
inputs:
  remediation_note:
    type: string
    default: ""
steps: []
""",
        encoding="utf-8",
    )

    engine = WorkflowEngine(tmp_path)
    with pytest.raises(ValueError, match="non-empty remediation_note"):
        engine.resume(state.run_id)

    completed = engine.resume(
        state.run_id, {"remediation_note": "Corrected the failing input"}
    )
    assert completed.status == RunStatus.COMPLETED
    assert completed.remediation is not None
    assert completed.remediation["failed_step_id"] == "failed-step"
    assert completed.remediation["previous_error"] == "recorded failure"
    assert completed.remediation["note"] == "Corrected the failing input"
    assert completed.remediation["recorded_at"]
