"""Regression tests for exclusive workflow-run ownership leases."""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime, timedelta

import pytest


def test_live_lease_rejects_a_second_resumer(tmp_path):
    from specify_cli.workflows.lease import ActiveRunLeaseError, RunLeaseManager

    manager = RunLeaseManager(tmp_path / "run")
    owner = manager.acquire()
    try:
        with pytest.raises(ActiveRunLeaseError, match="already owned"):
            manager.acquire()
    finally:
        assert owner.release()


def test_stale_lease_requires_explicit_recovery_reason(tmp_path):
    from specify_cli.workflows.lease import RunLeaseManager, StaleRunLeaseError

    manager = RunLeaseManager(tmp_path / "run")
    original = manager.acquire()
    lease_path = tmp_path / "run" / "lease.json"
    stale_record = json.loads(lease_path.read_text(encoding="utf-8"))
    stale_record["expires_at"] = (
        datetime.now(UTC) - timedelta(seconds=1)
    ).isoformat()
    lease_path.write_text(json.dumps(stale_record), encoding="utf-8")

    with pytest.raises(StaleRunLeaseError, match="expired lease"):
        manager.acquire()

    replacement = manager.acquire(recovery_reason="previous worker exited")
    try:
        assert replacement.recovered_lease is not None
        assert replacement.recovered_lease["owner_nonce"] == original.owner_nonce
        assert replacement.record["recovery_reason"] == "previous worker exited"
    finally:
        assert replacement.release()


def test_heartbeat_renews_the_owned_lease(tmp_path):
    from specify_cli.workflows.lease import RunLeaseManager, read_run_lease

    manager = RunLeaseManager(tmp_path / "run")
    owner = manager.acquire()
    try:
        before = read_run_lease(tmp_path / "run")
        assert before is not None
        renewed = manager.heartbeat(owner.owner_nonce)
        assert renewed["owner_nonce"] == owner.owner_nonce
        assert renewed["expires_at"] >= before["expires_at"]
    finally:
        assert owner.release()


def test_status_payload_reads_the_live_active_resumer(tmp_path):
    from specify_cli.workflows._commands import _workflow_run_payload
    from specify_cli.workflows.engine import RunState
    from specify_cli.workflows.lease import RunLeaseManager

    state = RunState(run_id="status-run", workflow_id="lease-test", project_root=tmp_path)
    owner = RunLeaseManager(state.runs_dir).acquire()
    try:
        payload = _workflow_run_payload(state)
        assert payload["active_resumer"]["owner_nonce"] == owner.owner_nonce
    finally:
        assert owner.release()


def test_engine_requires_reason_to_recover_a_stale_running_run(tmp_path):
    from specify_cli.workflows.base import RunStatus
    from specify_cli.workflows.engine import RunState, WorkflowEngine
    from specify_cli.workflows.lease import RunLeaseManager

    state = RunState(run_id="interrupted-run", workflow_id="lease-test", project_root=tmp_path)
    state.status = RunStatus.RUNNING
    state.save()
    (state.runs_dir / "workflow.yml").write_text(
        """
schema_version: "1.0"
workflow:
  id: "lease-test"
  name: "Lease test"
  version: "1.0.0"
steps: []
""",
        encoding="utf-8",
    )
    manager = RunLeaseManager(state.runs_dir)
    former_owner = manager.acquire()
    lease_path = state.runs_dir / "lease.json"
    stale_record = json.loads(lease_path.read_text(encoding="utf-8"))
    stale_record["expires_at"] = (
        datetime.now(UTC) - timedelta(seconds=1)
    ).isoformat()
    lease_path.write_text(json.dumps(stale_record), encoding="utf-8")

    engine = WorkflowEngine(tmp_path)
    with pytest.raises(ValueError, match="Cannot resume"):
        engine.resume(state.run_id)

    resumed = engine.resume(
        state.run_id, stale_recovery_reason="verified former worker exited"
    )
    assert resumed.status == RunStatus.COMPLETED
    assert any(event["event"] == "lease_reclaimed" for event in resumed.lease_history)
    assert former_owner.owner_nonce != resumed.lease_history[-2]["owner_nonce"]


def test_engine_blocks_a_concurrent_run_before_it_executes_a_custom_step(
    tmp_path, monkeypatch
):
    from specify_cli.workflows import STEP_REGISTRY
    from specify_cli.workflows.base import StepBase, StepResult
    from specify_cli.workflows.engine import WorkflowDefinition, WorkflowEngine
    from specify_cli.workflows.lease import ActiveRunLeaseError

    started = threading.Event()
    release_step = threading.Event()
    errors: list[BaseException] = []

    class BlockingStep(StepBase):
        type_key = "test-blocking-lease-step"

        def execute(self, config, context):
            started.set()
            assert release_step.wait(timeout=5)
            return StepResult(output={"owner": context.run_id})

    monkeypatch.setitem(STEP_REGISTRY, BlockingStep.type_key, BlockingStep())
    definition = WorkflowDefinition.from_string("""
schema_version: "1.0"
workflow:
  id: "lease-test"
  name: "Lease test"
  version: "1.0.0"
steps:
  - id: blocked
    type: test-blocking-lease-step
""")
    engine = WorkflowEngine(tmp_path)

    def run_first_owner():
        try:
            engine.execute(definition, run_id="shared-run")
        except Exception as exc:  # noqa: BLE001 - assertion below reports it
            errors.append(exc)

    worker = threading.Thread(target=run_first_owner)
    worker.start()
    assert started.wait(timeout=5)
    try:
        with pytest.raises(ActiveRunLeaseError, match="already owned"):
            WorkflowEngine(tmp_path).execute(definition, run_id="shared-run")
    finally:
        release_step.set()
        worker.join(timeout=5)

    assert not worker.is_alive()
    assert not errors
