# Loop Engine — 设计文档（spec）

- 日期：2026-06-24
- 状态：已与用户多轮收敛，进入实现
- 作者：Claude Code（拉姆）+ melee

## 1. 结论（一句话）

一个名为 `loop-engine` 的 Claude Code 技能：以 Addy Osmani 的 **Loop Engineering**（Plan→Act→Verify→Iterate）为骨架，搭一张**独立的、agent 无关的"圆桌会议桌" `.roundtable/`（黑板架构）**。桌上有一份所有 agent 都能自取的**知识库 KB**；**每个模型留在自己最强的原生壳里参与**——Claude Code（Opus，主持+执行）、`codex exec review`（GPT，验证员）、`hermes`（工具广度执行/可切 DeepSeek 做异质评审）。Claude 任主持但**不私藏上下文**，黑板是唯一共享真相。停止条件由验证裁决决定，触顶即交还人工。**全程项目内、零 Claude Code 底层改动。**

## 2. 设计演进（为什么是这版）

本设计经与用户多轮对话收敛，记录关键转折与被否方案，避免回潮：

1. **⚠️ SUPERSEDED（2026-06-24）：纯 CLI-subprocess 方案**（本 spec 初版）。Claude 直接 shell-out 调 codex/hermes，靠 brief 传上下文。否决原因：被下面的"原生壳 + 自取知识库"取代，但其"subprocess 驱动本地 agent""codex 当验证员""验证裁决即停"等内核被继承。
2. **被否：纯裸 API**（把别的模型剥成 API 调用）。否决原因：用户指出"GPT 在 codex 最强、Opus 在 Claude 最强"——厂商为自家模型调过壳，剥成裸 API 等于让高手用别人的兵器，丢失壳优化。
3. **被否：把 hermes 当身体塞外脑 / claude-code-router 让外脑附身 Claude subagent**。否决原因：router 劫持全局模型流量、要改 Claude Code 底层，会殃及用户**别的项目**——用户明确划红线。
4. **采纳：黑板架构圆桌**（用户提出）。会议桌完全独立，接各 agent（都在原生壳里），配 agent 无关知识库，参与者**自取所需（pull）**而非主持人喂瘦 prompt（push）——直接消解"外脑不懂项目 / prompt 总有遗漏"。
5. **⚠️ 修正（2026-06-24）：本体搬出 Claude，做成独立指挥程序 + TUI**。初版把"主持/编排"写进 Claude 技能(SKILL.md)，等于又把 Claude 拽回桌心当桌主——与"会议桌独立、agent 无关"自相矛盾。修正：
   - **本体 = 独立指挥程序 `conductor.py`（哑指挥）**：只管控制流（init→派活→执行→验证→迭代→停止），**不内嵌大脑**；智力全外包给被调用的座位。住在磁盘/PATH，可独立/无人值守跑，**不再是 Claude 技能**。
   - **总指挥(commander) = 用户每个任务指派的一个座位角色**（默认 claude，可指派 codex/hermes）：读花名册 `KB/roster.md`，按各 agent 特长产出派活计划（JSON）。Claude 由此**降为与 codex/hermes 平级的 headless 座位**（`claude -p`，仍带完整 Claude Code 工具壳+技能）。
   - **形态 = TUI 仪表盘**（Phase 2，项目内 venv + `rich`）：渲染座位实时状态/轮次/裁决。Phase 1 先做纯文本内核并验证。
   - SKILL.md 降级为可选启动器（不再是主持者）。

## 3. 依据

- **Loop Engineering（Addy Osmani, 2026-06）**：核心循环 Plan→Act→Observe/Verify→Iterate；铁律——*写代码的与验代码的须是两个 agent*、*无人值守的循环=无人值守地犯错，验证责任在人*；结构件——worktree 隔离、sub-agents（maker≠checker）、**外部状态/记忆（"agent 会忘，仓库不会"）**。主源 https://addyosmani.com/blog/loop-engineering/
- **黑板架构（Blackboard，经典 AI）**：一块共享知识结构，多个独立专家 agent 各看各取、各写各的，由控制组件协调。本设计的会议桌即黑板。
- **本地实测**：codex CLI 0.132.0，模型 gpt-5.5/xhigh，`codex exec review --uncommitted`（只读 diff、不动工作树）。hermes 模型 gpt-5.5 经同一 OpenAI Codex OAuth 后端（与 codex 同血统），`-z` 非交互、`--yolo`、`-w` worktree、`--provider`/`-m provider/model` 切后端；仅 DeepSeek 有直连 API key；gpt-5.5 可经 `hermes proxy`（OpenAI 兼容本地代理）当 API 打。Claude Code = Opus 4.8。

## 4. 角色（圆桌座位）

| 座位 | 壳（原生） | 血统 | 职责 | 为什么 |
|---|---|---|---|---|
| **主持 + 执行** | Claude Code | Opus 4.8 | 拆解、攒/刷新 KB、请座位、综合裁决、亲自动手改代码 | 握全上下文；Opus 文档定位即编排/综合/长上下文最强；改坏东西的活交给懂全局的它 |
| **验证员** | `codex exec review` | gpt-5.5 | 只读 diff + 自取 KB，挑致命缺陷，出 VERDICT | 专训 code review、SWE-bench 领跑、不动工作树；自己探仓库=自取，不吃瘦 prompt |
| **执行/第二评审** | `hermes -z` | gpt-5.5（可切 DeepSeek） | 工具广度活（浏览器/computer-use 等）；高风险时切 DeepSeek 做**异质血统**复审 | 工具集广；切 DeepSeek 得到与 Claude、gpt-5.5 都不同的血统，diversity 真实 |

**主持人去特权规矩**：Claude 知道的一切必须发布到 KB；不存在只有主持人看得到的"暗context"。各座位看到的是同一块黑板。

**分活原则**：握全上下文者干会改坏东西的活（执行=Claude）；上下文有损的外脑只干错了也不亏的活（审查/参谋）。

## 5. 架构

```
                      ┌──── .roundtable/（独立会议桌 = 黑板，项目内）────┐
                      │  KB/（agent 无关知识库，各座位自取 pull）          │
   ┌── 主持:Claude ──▶│   project.md / task.md / state.md /              │◀── 仓库源码本身
   │  （Opus）        │   diff.patch / test-results.txt                  │    也是 KB 一部分
   │                  │  minutes/（各轮各座位发言，互相可见→进下轮 KB）   │
   │                  │  roundtable.json（机读：轮次/参与者/裁决/计数）   │
   │                  └──────────────────────────────────────────────────┘
   │  Plan→Act→Verify→Iterate：
   │   ① 刷新 KB（kb-refresh.sh：重生成 diff、跑测试、bump state）
   │   ② 执行：Claude 亲自改；需 GPT 编码强项→seat-codex 执行子任务；需工具→seat-hermes
   │   ③ 验证：seat-codex.sh（codex 自读仓库+KB）+ 可选 seat-hermes 切 DeepSeek 复审 → 写 minutes
   │   ④ 主持读全部 minutes → 综合裁决 → BLOCK 回②修 / PASS 且测试过 → 收尾
   └─  记忆：checkpoint.sh 每轮 git 提交到 loop 分支 + 追加 state（仓库当记忆）
       停止：PASS✅ | 轮数≥N | token 超预算 | 同一发现连挂≥M → 出人话摘要交人工
```

## 6. 组件与接口

技能源在 `~/Documents/agents/skills/loop-engine/`。**默认项目内可用**；可选把该目录**复制**进 `~/.claude/skills/`（纯加法，不改任何现有文件）以全局 `/loop-engine` 调用。

| 文件 | 职责 | 接口约定 |
|---|---|---|
| `bin/conductor.py` | **本体·独立指挥程序（哑指挥）**：init→总指挥派活→分派执行→验证→迭代→停止 | `conductor.py --repo X --task "…" [--commander claude\|codex\|hermes] [--reviewer …] [--max-iters N] [--test-cmd …]`；`--dry-run` 经 `LOOP_DRY_RUN=1` |
| `bin/_lib.sh` | 共享：定位目标仓库、表目录、日志（走 stderr）、VERDICT 解析、配置默认 | 被 source |
| `bin/roundtable-init.sh` | 在目标仓库初始化 `.roundtable/`（KB 模板含花名册、state、loop 分支、exclude） | `roundtable-init.sh <repo> "<task>"` |
| `bin/kb-refresh.sh` | 刷新 KB 滚动部分：重生成 diff.patch、捕获测试输出 | `kb-refresh.sh <repo> [test_cmd]` |
| `bin/seat-claude.sh` | 请 Claude headless 入席（plan=总指挥派活 / exec / review），`claude -p` | `seat-claude.sh <repo> plan\|exec\|review ["<brief>"]` |
| `bin/seat-codex.sh` | 请 codex 入席（验证/执行），自读仓库+KB，写 minutes | `seat-codex.sh <repo> review\|exec ["<brief>"]`；退出码 `0=PASS 2=BLOCK 1=ERR`（裁决解析 `[P0]/[P1]`） |
| `bin/seat-hermes.sh` | 请 hermes 入席（执行/异质复审），可 `--provider`，写 minutes | `seat-hermes.sh <repo> exec\|review "<brief>" [provider model]` |
| `bin/checkpoint.sh` | git 检查点（loop 分支）+ 追加 state + bump 轮次 | `checkpoint.sh <repo> "<iter-summary>"` |
| `templates/*.md` | KB 模板：project / task / state / **roster（花名册）** | — |
| `SKILL.md` | 可选启动器（已从"主持者"降级；本体在 conductor.py） | `/loop-engine` 触发 |
| `tui/`（Phase 2） | rich.Live 仪表盘，渲染 conductor 的实时状态 | 项目内 `.venv` + `rich` |

## 7. 知识库（KB）格式

YAGNI：通用"每个 agent 都看得懂"的格式 = **仓库文件本身 + 朴素 markdown**，不用向量库/RAG。

- `KB/project.md`（稳定层）：项目是什么、架构图、关键文件、约定。
- `KB/task.md`：本轮任务 + 验收标准。
- `KB/state.md`（鲜活层）：当前轮次、已做、已决策、开放问题。
- `KB/diff.patch`：本轮改动（每轮重生成）。
- `KB/test-results.txt`：最新测试/构建输出。
- 仓库源码：各座位用自己的工具自读。

## 8. 配置（环境变量，均有默认）

| 变量 | 默认 | 说明 |
|---|---|---|
| `LOOP_MAX_ITERS` | `5` | 硬停轮数上限 |
| `LOOP_STUCK_LIMIT` | `2` | 同一发现连挂几次判定卡死 |
| `LOOP_REVIEW_PROVIDER` | `deepseek` | 异质复审用的 hermes provider |
| `LOOP_REVIEW_MODEL` | `deepseek-reasoner` | 异质复审模型（首次需 `hermes model` 确认实际 id） |
| `LOOP_TEST_CMD` | 空 | 任务的测试/构建命令；空则跳过自动测试由主持判断 |
| `LOOP_CODEX_EFFORT` | 空（沿用 `~/.codex/config.toml`） | codex 推理强度旋钮 `low\|medium\|high\|xhigh`；循环可按场景调档，验证关键步用高档、烟测用低档 |
| `LOOP_SEAT_TIMEOUT` | `600` | 单个座位调用的硬超时（秒）。超时→进程组强杀，记 ERR(124)。防一个 agent 卡死拖垮整个循环（codex `exec` 须 `-s workspace-write`，否则 read-only 沙箱会卡死等授权）|

## 9. 停止与人工边界

- **PASS**：codex 验证无 High/Critical **且** 测试/构建通过（高风险时还需 DeepSeek 复审 PASS）。
- **BLOCK**：有 High/Critical → 回 Plan/Act 修，重验。
- **硬停（交还人工）**：轮数 ≥ `LOOP_MAX_ITERS` / token 超预算 / 同一发现连挂 ≥ `LOOP_STUCK_LIMIT`。
- **强制先问人**：删除、覆盖、不可逆、花钱、对外发布——一律停下确认，绝不无人值守执行。
- 收尾出**人话摘要**：改了什么（diff 概要，治 comprehension debt）、各座位裁决、剩余风险、下一步触发点。

## 10. 安全红线（用户明确要求）

- **零 Claude Code 底层改动**：不碰 `~/.claude` 全局配置、不动 `ANTHROPIC_BASE_URL`、**不用 claude-code-router**。
- 一切活在目标项目内；DeepSeek 走直连 API、gpt-5.5 走 `hermes proxy` 本地小服务（用时起、用完关，不写 Claude 配置）。
- 可选的 `~/.claude/skills/loop-engine/` 安装是**纯新增目录**，不修改任何现有文件；用户若不愿，可纯项目内用路径调用。

## 11. 不做（YAGNI）

- 不做向量库/RAG 知识库（朴素 markdown + 仓库即可）。
- 不做 MCP server 封装、不做并行多 maker、不做 GUI。
- 不做"哑主持纯脚本"版（主持需综合判断，Claude 任之，靠去特权规矩中立化）。

## 12. 验收标准

1. `/loop-engine` 可触发，按 SKILL.md 跑通 Plan→Act→Verify→Iterate。
2. `seat-codex.sh <repo> review` 对故意写错的 diff 真实调起 codex 返回 `VERDICT: BLOCK`；对干净 diff 返回 `VERDICT: PASS`。
3. `seat-hermes.sh` 能真实调起 hermes 返回输出；切 DeepSeek 后端能返回复审。
4. KB 在 `.roundtable/` 持久化，`minutes/` 跨座位可见，git 检查点跨轮可续。
5. 收尾摘要含：改动概要、各座位裁决、剩余风险。
6. 全程未修改任何 `~/.claude` 现有文件 / 未设 `ANTHROPIC_BASE_URL`。
```
