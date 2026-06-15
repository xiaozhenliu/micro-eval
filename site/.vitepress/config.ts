import { defineConfig } from 'vitepress'
import { withMermaid } from 'vitepress-plugin-mermaid'

export default withMermaid(defineConfig({
  title: 'micro-eval',
  description: 'Evidence, not vibes. A local-first evaluation tool for small AI teams.',
  base: '/micro-eval/',

  ignoreDeadLinks: [
    /^https?:\/\/localhost/,
  ],

  head: [
    ['link', { rel: 'icon', href: '/micro-eval/favicon.ico' }],
    ['meta', { property: 'og:type', content: 'website' }],
    ['meta', { property: 'og:title', content: 'micro-eval' }],
    ['meta', { property: 'og:description', content: 'Evidence, not vibes. A local-first evaluation tool for small AI teams.' }],
    ['meta', { property: 'og:image', content: '/micro-eval/og-image.png' }],
  ],

  locales: {
    root: {
      label: 'English',
      lang: 'en',
    },
    zh: {
      label: '简体中文',
      lang: 'zh-CN',
      description: '用证据，不用体感。面向 AI 小团队的本地评测工具。',
      themeConfig: {
        nav: [
          { text: '指南', link: '/zh/guide/' },
          { text: '参考', link: '/zh/reference/cli' },
          { text: '示例', link: '/zh/examples/' },
        ],
        sidebar: {
          '/zh/guide/': [
            {
              text: '入门',
              items: [
                { text: 'micro-eval 是什么？', link: '/zh/guide/' },
                { text: '快速开始', link: '/zh/guide/getting-started' },
              ],
            },
            {
              text: '核心指南',
              items: [
                { text: '核心概念', link: '/zh/guide/core-concepts' },
                { text: '配置详解', link: '/zh/guide/configuration' },
                { text: '任务与验证', link: '/zh/guide/tasks' },
                { text: '执行层', link: '/zh/guide/execution' },
                { text: '评分系统', link: '/zh/guide/evaluation' },
                { text: '决策与 Caveat', link: '/zh/guide/decision' },
                { text: 'Workspace 隔离', link: '/zh/guide/workspace-isolation' },
                { text: '趋势分析', link: '/zh/guide/trend-analysis' },
                { text: '安全模型', link: '/zh/guide/security' },
              ],
            },
          ],
          '/zh/reference/': [
            {
              text: '参考手册',
              items: [
                { text: 'CLI 命令', link: '/zh/reference/cli' },
                { text: 'eval.yaml Schema', link: '/zh/reference/eval-yaml' },
                { text: 'task.yaml Schema', link: '/zh/reference/task-yaml' },
                { text: '数据模型', link: '/zh/reference/data-model' },
                { text: 'API 路由', link: '/zh/reference/api-routes' },
                { text: 'Web UI', link: '/zh/reference/web-ui' },
              ],
            },
          ],
          '/zh/examples/': [
            {
              text: '示例',
              items: [
                { text: '总览', link: '/zh/examples/' },
                { text: 'Agent 代码修复对决', link: '/zh/examples/agent-codefix-showdown' },
                { text: '多任务矩阵', link: '/zh/examples/multi-task-matrix' },
                { text: 'Git Workspace 隔离', link: '/zh/examples/git-workspace-isolation' },
              ],
            },
          ],
        },
      },
    },
  },

  themeConfig: {
    logo: '/logo.svg',
    nav: [
      { text: 'Guide', link: '/guide/' },
      { text: 'Reference', link: '/reference/cli' },
      { text: 'Examples', link: '/examples/' },
    ],
    sidebar: {
      '/guide/': [
        {
          text: 'Introduction',
          items: [
            { text: 'What is micro-eval?', link: '/guide/' },
            { text: 'Getting Started', link: '/guide/getting-started' },
          ],
        },
        {
          text: 'Core Guide',
          items: [
            { text: 'Core Concepts', link: '/guide/core-concepts' },
            { text: 'Configuration', link: '/guide/configuration' },
            { text: 'Tasks & Expectations', link: '/guide/tasks' },
            { text: 'Execution', link: '/guide/execution' },
            { text: 'Evaluation & Scoring', link: '/guide/evaluation' },
            { text: 'Decision & Caveats', link: '/guide/decision' },
            { text: 'Workspace Isolation', link: '/guide/workspace-isolation' },
            { text: 'Trend Analysis', link: '/guide/trend-analysis' },
            { text: 'Security Model', link: '/guide/security' },
          ],
        },
      ],
      '/reference/': [
        {
          text: 'Reference',
          items: [
            { text: 'CLI Commands', link: '/reference/cli' },
            { text: 'eval.yaml Schema', link: '/reference/eval-yaml' },
            { text: 'task.yaml Schema', link: '/reference/task-yaml' },
            { text: 'Data Model', link: '/reference/data-model' },
            { text: 'API Routes', link: '/reference/api-routes' },
            { text: 'Web UI', link: '/reference/web-ui' },
          ],
        },
      ],
      '/examples/': [
        {
          text: 'Examples',
          items: [
            { text: 'Overview', link: '/examples/' },
            { text: 'Agent Codefix Showdown', link: '/examples/agent-codefix-showdown' },
            { text: 'Multi-Task Matrix', link: '/examples/multi-task-matrix' },
            { text: 'Git Workspace Isolation', link: '/examples/git-workspace-isolation' },
          ],
        },
      ],
    },
    socialLinks: [
      { icon: 'github', link: 'https://github.com/xiaozhenliu/micro-eval' },
    ],
    search: {
      provider: 'local',
    },
    footer: {
      message: 'Released under the Apache-2.0 License.',
      copyright: 'Copyright © 2026 micro-eval contributors',
    },
  },
}))
