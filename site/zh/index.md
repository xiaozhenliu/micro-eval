---
layout: home
hero:
  name: micro-eval
  text: 用证据，不用体感。
  tagline: 面向 AI 小团队的本地评测工具，让 agent/skill/prompt 对比可量化、可溯源、可复现。
  actions:
    - theme: brand
      text: 快速开始
      link: /zh/guide/getting-started
    - theme: alt
      text: 在 GitHub 上查看
      link: https://github.com/xiaozhenliu/micro-eval
  image:
    src: /logo.svg
    alt: micro-eval
features:
  - icon: 🧪
    title: 矩阵对比
    details: 将 tasks × configurations × repetitions 展开为 canonical 执行矩阵。用 pass@k、cost、latency 对比 baseline 和 candidate。
  - icon: 🔒
    title: 同起点保证
    details: 每个 cell 从可复现的起点运行。Snapshot 不匹配会降级 decision——不做虚假的赢家声明。
  - icon: 🛡️
    title: 多级沙箱
    details: 默认 git worktree 隔离。OS 策略沙箱（Seatbelt/Bubblewrap）或远程 VM（E2B/Modal）用于不受信 agent。
  - icon: 📊
    title: 受保护的决策
    details: 决策附带证据链和 caveat。不确定就是不确定——而不是沉默。
  - icon: 🔍
    title: 完整证据链
    details: Decision → Task → Trace → Diff → Cost → Artifact。每个结论都可追溯到原始证据。
  - icon: 📈
    title: 趋势分析
    details: 跨 run 追踪 configuration 表现。Drift-aware breakpoint 标记比较何时变得无效。
  - icon: 👥
    title: 团队服务器
    details: 通过隔离 Workspace、串行队列和只读模板库在团队间共享评测。可信内网部署——只需一台机器，无需额外基础设施。
---
