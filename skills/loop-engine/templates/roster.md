# 座位花名册（KB — 各 agent 的特长，供总指挥按此派活）

> 总指挥（plan 阶段）读这里，把子任务按特长分派。可按需增删座位或调整描述。

## claude（Claude Code · Opus 4.8 · Anthropic 血统）
- **强**：编排/规划/综合、长上下文、多文件重构、自我纠错。
- **宜接**：总指挥本身、会改坏东西/需全局判断的执行、最终综合裁决。
- 调用：`seat-claude.sh <repo> plan|exec|review`（headless `claude -p`，带完整 Claude Code 工具壳+技能）。

## codex（OpenAI Codex CLI · gpt-5.5 · xhigh）
- **强**：代码验证/挑致命缺陷（自带 `codex exec review`）、SWE-bench 级编码、终端自治。
- **宜接**：独立代码验证（首选验证席）、单文件强编码子任务。
- **注意**：与 hermes 默认同为 gpt-5.5 血统；裁决靠其原生 `[P0]/[P1]` 标记。
- 调用：`seat-codex.sh <repo> review|exec`。

## hermes（NousResearch Hermes · gpt-5.5，可切 DeepSeek · 工具巨兽）
- **强**：工具广度（浏览器/computer-use/消息/记忆/cron/MCP）、长工具链、可换后端。
- **宜接**：工具/环境活、外部检查；**切 DeepSeek 时**做与 claude/gpt-5.5 都不同血统的**异质复审**。
- 调用：`seat-hermes.sh <repo> exec|review "<brief>" [provider] [model]`（异质复审传 `deepseek deepseek-reasoner`）。

---
（新增本地 agent：加一节，写清"强/宜接/调用方式"，总指挥即可纳入分派。）
