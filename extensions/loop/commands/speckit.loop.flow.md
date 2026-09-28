---
name: speckit-loop-flow
description: Start or resume the registered Spec Kit loop workflows from an active Codex session.
compatibility: Requires an initialized Spec Kit project with the loop extension and the registered workflow assets.
---

# Spec Kit Loop Flow

Use this skill as the in-session bridge to `specify workflow run`, `status`, and
`resume`. It does not duplicate workflow policy: the registered workflow YAML
and persisted loop contract remain authoritative.

## Inputs

Accept repeatable terminal-style inputs and an optional selected workflow:

```text
$speckit-loop-flow -i integration=codex -i spec="Describe the feature"
$speckit-loop-flow workflow=speckit-loop-yolo -i integration=codex -i spec="Explore the feature"
$speckit-loop-flow run_id=RUN_ID -i plan_verdict=approve
```

- `workflow` accepts only `speckit-loop` or `speckit-loop-yolo`; default to
  `speckit-loop` when it is absent.
- `spec` is required for a new run and must be non-empty.
- `integration` accepts `codex` or `auto`; retain the workflow default when absent.
- `run_id` selects an existing paused or failed run for status and resume.
- `remediation_note` is required before resuming a failed stage and is retained
  with its failure context.

## Procedure

1. Parse only the documented `-i key=value`, `workflow=`, and `run_id=` fields.
   Reject unknown workflow IDs, blank `spec`, malformed inputs, and unsupported
   integrations before starting a run.
2. For a new run, invoke the selected registered workflow with:

   ```bash
   specify workflow run WORKFLOW_ID -i integration=VALUE -i spec=VALUE --json
   ```

   Keep each input as a distinct argument. Never interpolate feature text,
   agent output, or workflow-state contents into a shell command.
3. For `run_id`, first use `specify workflow status RUN_ID --json`, then use
   `python3 .specify/workflows/steps/loop-state/state_adapter.py --status RUN_ID`
   when the adapter state exists. Report the native operational status and the
   separate durable outcome; do not resume an `incomplete` or `incompatible`
   outcome as if it were complete. If a run is `running`, reject the request
   without changing state. The pinned engine atomically claims its active-resumer lease; the active resumer lock precedes a `running` transition. For an expired lease, require a factual `--recover-stale-lease` reason and report the recorded recovery evidence from JSON status.
4. Resume only paused or failed runs using `specify workflow resume RUN_ID` with
   the exact applicable verdict or remediation input. A retry of a failed stage
   must include a non-empty `remediation_note` and must preserve prior inputs
   and completed stages.
5. Report the selected workflow ID, run ID, operational status, durable outcome
   when present, and exactly one next action. For a governed review pause,
   report the matching verdict input; never supply or fabricate human sign-off.

## Boundaries

- The governed workflow has specification, plan, and completion sign-off gates.
- `speckit-loop-yolo` has no human approval or sign-off gates, but still needs
  independent checker-pass evidence and no blocking comprehension debt.
- The workflow never controls ROS, a robot controller, Docker privileges, or
  other elevated host capabilities.
