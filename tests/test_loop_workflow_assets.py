"""Contracts for the bundled Loop Engineering extension and workflows."""

from __future__ import annotations

from pathlib import Path

import yaml
import pytest
from typer.testing import CliRunner


ROOT = Path(__file__).resolve().parent.parent


def test_loop_extension_and_workflows_are_bundled() -> None:
    from specify_cli import _locate_bundled_extension, _locate_bundled_workflow
    from specify_cli.extensions import ExtensionManifest
    from specify_cli.workflows import get_step_type
    from specify_cli.workflows.engine import WorkflowDefinition, validate_workflow

    extension = _locate_bundled_extension("loop")
    assert extension == ROOT / "extensions" / "loop"
    manifest = ExtensionManifest(extension / "extension.yml")
    assert manifest.id == "loop"
    assert manifest.version == "1.1.0"
    assert {command["name"] for command in manifest.commands} >= {
        "speckit.loop.define",
        "speckit.loop.run",
        "speckit.loop.check",
        "speckit.loop.guard",
        "speckit.loop.status",
        "speckit.loop.flow",
    }
    assert get_step_type("loop-state") is not None

    for workflow_id in ("speckit-loop", "speckit-loop-yolo"):
        workflow_dir = _locate_bundled_workflow(workflow_id)
        assert workflow_dir == ROOT / "workflows" / workflow_id
        definition = WorkflowDefinition.from_yaml(workflow_dir / "workflow.yml")
        assert definition.id == workflow_id
        assert validate_workflow(definition) == []


@pytest.mark.parametrize("workflow_id", ("speckit-loop", "speckit-loop-yolo"))
def test_bundled_loop_workflow_installs_without_a_catalog(
    tmp_path: Path, monkeypatch, workflow_id: str
) -> None:
    from specify_cli import app

    (tmp_path / ".specify").mkdir()
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["workflow", "add", workflow_id])

    assert result.exit_code == 0, result.output
    workflow_path = tmp_path / ".specify" / "workflows" / workflow_id / "workflow.yml"
    assert workflow_path.is_file()
    installed = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    assert installed["workflow"]["id"] == workflow_id
