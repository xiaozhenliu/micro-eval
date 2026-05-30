"""Scoring engine - wraps DeepEval for metric evaluation."""

from __future__ import annotations

from typing import Optional

from micro_eval.models.schema import RunResult, Task, TaskStatus


class Scorer:
    """Scores agent outputs against expected results and rubrics."""

    def score(self, result: RunResult, task: Task) -> float:
        """Score a run result against a task's expected output.

        Returns a float between 0.0 and 1.0.
        For MVP, uses exact match when expected_output is set.
        """
        if result.status in (TaskStatus.error, TaskStatus.timeout):
            return 0.0

        if task.expected_output is None:
            # No expected output defined - pass/fail only
            return 1.0 if result.status == TaskStatus.passed else 0.0

        # Exact match scoring (normalized)
        output = result.output_summary.strip()
        expected = task.expected_output.strip()

        if output == expected:
            return 1.0

        # Partial match: check if expected is contained in output
        if expected and expected in output:
            return 0.8

        return 0.0

    def judge_pass_fail(
        self, result: RunResult, task: Task, threshold: float = 0.5
    ) -> TaskStatus:
        """Determine pass/fail based on score threshold."""
        if result.status in (TaskStatus.error, TaskStatus.timeout):
            return result.status

        score = self.score(result, task)
        return TaskStatus.passed if score >= threshold else TaskStatus.failed
