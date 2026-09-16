"""Spec Kit custom step that enforces the project loop-state contract."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from specify_cli.workflows.base import StepBase, StepContext, StepResult, StepStatus

from .state_adapter import (
    LoopStateError,
    sync_lifecycle_state,
    sync_loop_state,
    validate_new_run_inputs,
)


class LoopStateStep(StepBase):
    """Project-local bridge from loop evidence to workflow-safe decisions."""

    type_key = "loop-state"

    def validate(self, config: dict[str, Any]) -> list[str]:
        errors = super().validate(config)
        action = config.get("action")
        if action not in {"validate-input", "initialize", "evaluate", "record-signoff", "enforce"}:
            errors.append(
                "Loop-state step requires action validate-input, initialize, evaluate, record-signoff, or enforce."
            )
        if config.get("variant") not in {"governed", "yolo"}:
            errors.append("Loop-state step requires variant governed or yolo.")
        return errors

    def observe_persisted_run_state(
        self,
        config: dict[str, Any],
        state: dict[str, Any],
        project_root: str,
    ) -> None:
        """Keep the durable loop sidecar aligned with native lifecycle writes."""
        variant = config.get("variant")
        if variant not in {"governed", "yolo"}:
            raise LoopStateError("State observer requires variant governed or yolo.")
        sync_lifecycle_state(Path(project_root), state, variant=variant)

    def execute(self, config: dict[str, Any], context: StepContext) -> StepResult:
        action = config.get("action")
        variant = config.get("variant")
        if action not in {"validate-input", "initialize", "evaluate", "record-signoff", "enforce"}:
            return StepResult(status=StepStatus.FAILED, error="Invalid loop-state action.")
        if variant not in {"governed", "yolo"}:
            return StepResult(status=StepStatus.FAILED, error="Invalid loop-state variant.")
        if context.project_root is None or context.run_id is None:
            return StepResult(
                status=StepStatus.FAILED,
                error="Loop-state step requires a project root and workflow run ID.",
            )

        if action == "validate-input":
            try:
                validate_new_run_inputs(context.inputs)
            except LoopStateError as exc:
                return StepResult(status=StepStatus.FAILED, error=str(exc))
            return StepResult(
                status=StepStatus.COMPLETED,
                output={"validated": True, "next_action": "specify"},
            )

        try:
            state = sync_loop_state(
                Path(context.project_root),
                context.run_id,
                variant=variant,
                action=action,
                completion_verdict=context.inputs.get("completion_verdict", ""),
            )
        except LoopStateError as exc:
            return StepResult(status=StepStatus.FAILED, error=str(exc))

        outcome = state["outcome"]
        # ``evaluate`` is a read/derive stage. It must return its durable
        # next_action to the workflow's control-flow steps rather than failing
        # before a bounded maker/checker loop can route a checker failure back
        # to the maker. ``enforce`` is the terminal branch: it stops any
        # incomplete or incompatible outcome after routing has decided no
        # permitted success path remains.
        if action == "enforce":
            may_continue = outcome == "completed"
        else:
            may_continue = action in {"initialize", "evaluate"} or outcome in {"pending", "completed"}
        if may_continue:
            return StepResult(status=StepStatus.COMPLETED, output=state)
        return StepResult(
            status=StepStatus.FAILED,
            output=state,
            error=f"Loop outcome is {outcome}; next action: {state['next_action']}.",
        )
