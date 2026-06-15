---
layout: home
hero:
  name: micro-eval
  text: Evidence, not vibes.
  tagline: A local-first evaluation tool for small AI teams to compare agents, skills, and prompts with reproducible evidence.
  actions:
    - theme: brand
      text: Get Started
      link: /guide/getting-started
    - theme: alt
      text: View on GitHub
      link: https://github.com/xiaozhenliu/micro-eval
  image:
    src: /logo.svg
    alt: micro-eval
features:
  - icon: 🧪
    title: Matrix Comparison
    details: Expand tasks × configurations × repetitions into a canonical run matrix. Compare baseline and candidate with pass@k, cost, and latency.
  - icon: 🔒
    title: Same-Start Guarantee
    details: Every cell runs from a reproducible starting point. Snapshot mismatch downgrades the decision — no fake winner claims.
  - icon: 🛡️
    title: Multi-Level Sandbox
    details: Git worktree isolation by default. OS policy sandbox (Seatbelt/Bubblewrap) or remote VM (E2B/Modal) for untrusted agents.
  - icon: 📊
    title: Guarded Decisions
    details: Decisions come with evidence chains and caveats. Inconclusive is a valid answer — not silence.
  - icon: 🔍
    title: Full Evidence Chain
    details: Decision → Task → Trace → Diff → Cost → Artifact. Every conclusion traces back to raw evidence.
  - icon: 📈
    title: Trend Analysis
    details: Track configuration performance across runs. Drift-aware breakpoints flag when comparisons become invalid.
---
