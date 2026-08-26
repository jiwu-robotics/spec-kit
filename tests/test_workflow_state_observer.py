"""Executable contract for opt-in persisted workflow-state observers."""

from __future__ import annotations


def test_custom_observer_receives_every_persisted_terminal_transition(
    tmp_path, monkeypatch
):
    from specify_cli.workflows import STEP_REGISTRY
    from specify_cli.workflows.base import StepBase, StepResult, StepStatus
    from specify_cli.workflows.engine import WorkflowDefinition, WorkflowEngine

    snapshots: list[dict[str, object]] = []

    class ObserverStep(StepBase):
        type_key = "test-state-observer"

        def execute(self, config, context):
            return StepResult(status=StepStatus.PAUSED)

        def observe_persisted_run_state(self, config, state, project_root):
            assert config["variant"] == "test"
            assert project_root == str(tmp_path)
            snapshots.append(state)

    monkeypatch.setitem(STEP_REGISTRY, ObserverStep.type_key, ObserverStep())
    definition = WorkflowDefinition.from_string("""
schema_version: "1.0"
workflow:
  id: "observer-test"
  name: "Observer test"
  version: "1.0.0"
  state_observer:
    type: test-state-observer
    variant: test
steps:
  - id: pause
    type: test-state-observer
""")

    state = WorkflowEngine(tmp_path).execute(definition, run_id="observer-run")

    assert state.status.value == "paused"
    assert snapshots
    assert snapshots[0]["status"] == "running"
    assert any(snapshot["current_step_id"] == "pause" for snapshot in snapshots)
    assert any(snapshot["status"] == "paused" for snapshot in snapshots)
