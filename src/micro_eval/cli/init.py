"""Initialize a local micro-eval project."""

from __future__ import annotations

from pathlib import Path

import typer

CANONICAL_EVAL_YAML = """# Canonical micro-eval configuration.
project_name: demo-agent-eval
description: Local deterministic starter project

configurations:
  - id: baseline
    name: echo-baseline
    role: baseline
    repetitions: 1
    agent:
      name: echo-baseline
      command: ["cat"]
      input_mode: stdin
      output_mode: stdout
      timeout_s: 10
      env: {}
  - id: candidate
    name: echo-candidate
    role: candidate
    repetitions: 1
    agent:
      name: echo-candidate
      command: ["cat"]
      input_mode: stdin
      output_mode: stdout
      timeout_s: 10
      env: {}

tasks:
  - tasks/hello.yaml
output_dir: .micro-eval/runs

guardrails:
  max_concurrency: 4
  timeout_s: 30
  output_cap_bytes: 1048576
  artifact_cap_bytes: 5242880

evaluation:
  comparison_subject: null
  task_set_version: ""
  success_criteria:
    - Validator expectations pass and any caveats are reviewed.
  budget: null
  decision_threshold: null
  inconclusive_policy: warn
  min_repetitions: 1
  required_evaluators: [validator]
  denominator_policy: include_failed
"""

STARTER_TASK = """id: hello
title: Hello echo
name: Hello echo
description: Verify a local agent can echo stdin.
input_payload: "Hello, micro-eval!"
expected_output: "Hello, micro-eval!"
expectations:
  - type: contains
    stream: output
    value: "Hello, micro-eval!"
rubric: Output should contain the input exactly.
business_impact_tier: 3
tags: [smoke, deterministic]
"""

FILE_OUTPUT_TASK = """id: file-output
name: File output contract
description: Verify output_mode=file agents write MICRO_EVAL_OUTPUT_FILE.
input_payload: "Write this exact sentence to the output file."
expected_output: "Write this exact sentence to the output file."
expectations:
  - type: contains
    stream: output
    value: "Write this exact sentence to the output file."
rubric: The output file should contain the requested sentence exactly.
business_impact_tier: 3
tags: [template, file-output]
"""

COMMAND_VALIDATION_TEMPLATE = """id: command-validation
name: Command validation template
description: Demonstrates safe argv validation against the cell output directory.
input_payload: "hello"
expectations:
  - type: command
    command: ["python", "-c", "from pathlib import Path; assert Path('stdout.txt').exists()"]
    cwd: "{output_dir}"
    timeout_s: 5
rubric: Validation command must be argv-only and scoped to the cell output directory.
business_impact_tier: 4
tags: [template, command-validation]
"""


def init_command(
    force: bool = typer.Option(False, "--force", help="Overwrite existing eval.yaml and starter task"),
) -> None:
    """Create eval.yaml and a starter task."""
    config_path = Path("eval.yaml")
    task_dir = Path("tasks")
    task_path = task_dir / "hello.yaml"
    templates_dir = task_dir / "templates"
    file_output_task_path = templates_dir / "file-output.yaml"
    command_template_path = templates_dir / "command-validation.yaml"
    if (config_path.exists() or task_path.exists() or file_output_task_path.exists()) and not force:
        typer.echo("Project files already exist. Use --force to overwrite.", err=True)
        raise typer.Exit(1)
    task_dir.mkdir(parents=True, exist_ok=True)
    templates_dir.mkdir(parents=True, exist_ok=True)
    config_path.write_text(CANONICAL_EVAL_YAML)
    task_path.write_text(STARTER_TASK)
    file_output_task_path.write_text(FILE_OUTPUT_TASK)
    command_template_path.write_text(COMMAND_VALIDATION_TEMPLATE)
    typer.echo("Created eval.yaml, tasks/hello.yaml, and starter templates under tasks/templates/")
