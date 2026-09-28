---
title: "micro-eval UX Guidelines"
language: en
authoritative: true
date: 2026-06-02
updated_at: 2026-09-27T16:00+08:00
status: draft
type: engineering-guidelines
tags:
  - engineering
  - ux
  - micro-eval
---

# micro-eval UX Guidelines

micro-eval is a local evaluation workbench, not a marketing site. The UI helps users quickly judge whether an agent / skill change is worth pursuing.

## Product Feel

- High information density without chaos.
- Prefer matrices, tables, states, and evidence chains over large decorative areas.
- The default first screen is actionable run / matrix / decision content — no landing page.
- Visual hierarchy serves three actions: compare, drill down, review.

## Decision UX

Users must see at a glance:

- The current verdict / DecisionStatus.
- Whether results are comparable.
- Which caveats limit the conclusion.
- Key differences across baseline / candidate or configurations.
- Pass rate, latency, cost-if-present.
- Which tasks drive mixed / regressed / inconclusive outcomes.
- Entry points into the evidence chain.

Not allowed:

- Highlighting a winner while the snapshot gate failed.
- Treating a low sample as an ordinary success.
- Green/red hints implying conclusions without evidence.
- Presenting raw stdout as the scoring explanation.

## Result Matrix UX

MatrixHeatmap is the core MVP surface.

- Rows: tasks.
- Columns: configurations.
- Cells: status, score/pass_fail, latency, cost-if-present, caveat markers.
- Repetitions: aggregated display with drill-down to a single rep.
- Failed cells must state the failure kind: timeout, nonzero, crash, validation failed, not comparable.

## Artifact and Evidence UX

- ArtifactViewer shows raw stdout/stderr/diff/files.
- Evidence views show structured summaries, sources, severity, and the linked cell.
- DecisionSummary drills down from evidence to artifact — never the reverse, making users guess conclusions from artifacts.
- Secret-redaction placeholders are clearly visible without exposing the original value.

## Forms and Controls

- Binary options use checkboxes / toggles.
- Enum options use selects / segmented controls.
- Numeric parameters use inputs / sliders / steppers.
- Tool buttons use icons + tooltips.
- Table filtering and sorting are visible and reversible.
- Long explanatory text never replaces clear states and controls.
