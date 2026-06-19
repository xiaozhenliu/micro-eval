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
                { text: '设计体系', link: '/zh/guide/design-system' },
              ],
            },
            {
              text: '使用指南',
              items: [
                { text: '定义任务', link: '/zh/guide/tasks' },
                { text: '配置对比组', link: '/zh/guide/configuration' },
                { text: '运行与结果', link: '/zh/guide/execution' },
                { text: '评分系统', link: '/zh/guide/evaluation' },
                { text: '做出决策', link: '/zh/guide/decision' },
              ],
            },
            {
              text: '进阶',
              items: [
                { text: 'Workspace 与沙箱', link: '/zh/guide/workspace-isolation' },
                { text: '趋势分析', link: '/zh/guide/trend-analysis' },
                { text: '团队服务器', link: '/zh/guide/team-server' },
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
          text: 'Get Started',
          items: [
            { text: 'What is micro-eval?', link: '/guide/' },
            { text: 'Getting Started', link: '/guide/getting-started' },
            { text: 'Design System', link: '/guide/design-system' },
          ],
        },
        {
          text: 'Using micro-eval',
          items: [
            { text: 'Defining Tasks', link: '/guide/tasks' },
            { text: 'Configuring Comparisons', link: '/guide/configuration' },
            { text: 'Running & Results', link: '/guide/execution' },
            { text: 'Evaluation & Scoring', link: '/guide/evaluation' },
            { text: 'Making Decisions', link: '/guide/decision' },
          ],
        },
        {
          text: 'Advanced',
          items: [
            { text: 'Workspace & Sandboxing', link: '/guide/workspace-isolation' },
            { text: 'Trend Analysis', link: '/guide/trend-analysis' },
            { text: 'Team Server', link: '/guide/team-server' },
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
