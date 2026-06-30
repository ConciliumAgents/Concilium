---
name: loop-engine
description: "Run an Addy-Osmani-style Loop Engineering round table from Claude Code: Claude chairs (plans + verifies) a plan→act→verify→iterate loop on a shared blackboard (.roundtable/), while heterogeneous fast seats hermes (DeepSeek) and kimi (K2.7) execute in their own native CLIs; maker≠checker, verified by an independent seat. Claude stays out of headless exec (it times out at 600s) — large core edits are written by the chair directly in the main conversation. codex is a verifier only when reachable. Also runnable fully-automatically via bin/conductor.py. Use for autonomous, verified, multi-agent code-change loops."
---

# Loop Engine — 圆桌主持协议

你（Claude）是这张圆桌的**主持人（指挥 plan + 验证 review）**。参考 Addy Osmani 的 Loop Engineering（Plan→Act→Verify→Iterate），通过共享黑板 `.roundtable/` 协调飞毛腿执行席 hermes（DeepSeek）、kimi（K2.7）与（可达时的）codex 验证席在各自原生壳里参与。原始设计 `docs/superpowers/specs/2026-06-24-loop-engine-design.md`；**提速（claude 退 exec）、降级容错、座位画像等演进见 `2026-06-27-roundtable-speedup-design.md`、`2026-06-28-roster-profiles-design.md`——分工以本文件 + `KB/roster.md` 实战画像为准。**

补充文档：Agent MoA 的定位见 `docs/loop-engine/agent-moa-positioning.md`；座位输入/输出契约见 `docs/loop-engine/seat-contract.md`；离线验证与评测入口见 `bin/seat-contract-validate.py`、`bin/eval-roundtable.py`、`bin/report-session.py`。

## 两种用法
- **主持模式（本文件）**：你在对话里逐步驱动 plan→act→verify，用 `bin/seat-*.sh` 调座位；会改坏东西的大块核心代码**由你在主对话里亲写**（握全上下文、无超时）。
- **自动模式**：`bin/conductor.py --repo <repo> --task "<任务+验收标准>"` 一条命令全自动跑完整循环（总指挥 plan → 飞毛腿 exec → reviewer 验证 → 迭代到 PASS）。claude 退 headless exec、reviewer 自动解析、降级容错、按座位画像派活都在此模式（细节见上述 spec）。其他项目里走 CLI（见 `~/.claude/CLAUDE.md` 圆桌速查）。

## 铁律（先读，违反则整套失效）

1. **maker ≠ checker**：写/改代码的座位，必须由**独立座位**验证，不许自己给自己盖章。验证席优先异质飞毛腿（hermes/kimi），codex 可达时亦可；自动模式 `--reviewer` 留空＝自动解析（异质优先 hermes、claude 兜底）。
2. **主持人不私藏上下文**：你知道的一切（任务、决策、架构理解）必须落到 `.roundtable/KB/`。其它座位看到的是同一块黑板。绝不存在"只有你看得到的暗 context"。
3. **分活原则（执行交飞毛腿，claude 退 headless exec）**：headless 执行交飞毛腿（hermes/kimi）；**claude 不入 headless exec 座位——揽执行会撞 600s 超时空转**，改任指挥(plan)+验证(review)。会改坏东西的大块核心代码，由主持人**在主对话里亲写**（无超时，这是"带外"通道，不占圆桌 exec 座位）。上下文有损的外脑只干"错了也不亏"的活（审查/参谋）。
4. **无人值守 = 无人值守地犯错**：循环可自主跑，但停止由验证裁决决定；删除/覆盖/不可逆/花钱/对外发布，一律停下问人。
5. **零底层改动**：不碰 `~/.claude` 全局配置、不设 `ANTHROPIC_BASE_URL`、不用 claude-code-router。一切活在目标项目内。

## 准备：确认参与方

脚本在本技能的 `bin/` 下。开工前先确认环境（缺谁就降级，不要硬跑）：

```
hermes --version       # 飞毛腿执行 / 异质复审（DeepSeek 血统）
kimi --version         # 飞毛腿执行 / 严格验证（K2.7，Moonshot 异质）
codex --version        # 验证席（注：当前 chatgpt.com 后端常 websocket tls 故障、多不可达，届时自动排除）
```

**座位现状＝派活依据**以 `KB/roster.md`（合并了 `roundtable-memory/ROSTER-PROFILES.md` 实战画像）为准：claude 退 exec 任指挥+验证、飞毛腿 hermes/kimi 干 exec、codex 当前不可达。

环境变量（可选）：`LOOP_MAX_ITERS`(5) `LOOP_SEAT_TIMEOUT`(600，headless 座位默认硬超时) `LOOP_SEAT_TIMEOUT_<SEAT>` / `LOOP_SEAT_TIMEOUT_<SEAT>_<MODE>`（按座位/模式覆盖；如 `LOOP_SEAT_TIMEOUT_CLAUDE_REVIEW=600`） `LOOP_TEST_CMD` `LOOP_REVIEW_PROVIDER`/`LOOP_REVIEW_MODEL`(hermes 异质复审用) `LOOP_USE_ROUNDTABLE_MEMORY`(默认关；开则注入 git 化中立记忆/教训)。

## 流程（每一步都建 todo 跟踪）

### 0. 开桌
- 跟用户确认：**目标仓库路径**、**任务**、**验证命令**（测试/构建）、**是否高风险**（删除/迁移/对外）。
- `bin/roundtable-init.sh <repo> "<task>"` 初始化会议桌。
- **亲自填好** `.roundtable/KB/project.md`（架构地图）与 `KB/task.md`（任务+可验证的验收标准）——这是你"不私藏上下文"的体现。建议在 `loop-engine/<slug>` 分支上工作（init 已建好，手动 `git switch` 切入）。

### 1. PLAN
- 读仓库与 KB，拆解本轮要做什么，把方案与本轮验收写进 `KB/task.md` / `KB/state.md`。**按 roster.md 的实战画像派活**（执行优先飞毛腿）。
- （可选）高风险或拿不准时，先请一个座位出"方案二意见"：`bin/seat-hermes.sh <repo> review "先别看 diff，评估这个计划是否合理：……"` 或 `bin/seat-kimi.sh`。

### 2. ACT
- **会改坏东西的大块核心代码：你自己在主对话里写**（握全上下文、无超时——铁律 3 的"带外亲写"）。
- 独立子任务派飞毛腿 headless 执行：`bin/seat-hermes.sh <repo> exec "<任务>"`（工具/环境广度）或 `bin/seat-kimi.sh <repo> exec "<子任务>"`（强编码）。
- **别派 claude / codex 进 headless exec**（claude 会 600s 超时空转、codex 当前不可达）。

### 3. 刷新黑板
- `bin/kb-refresh.sh <repo> "<测试命令>"`：重生成 `KB/diff.patch`、跑测试写 `KB/test-results.txt`。这样验证席能自取到最新事实。

### 4. VERIFY（核心，maker≠checker）
- 独立验证席（异质飞毛腿）：`bin/seat-hermes.sh <repo> review` 或 `bin/seat-kimi.sh <repo> review`——自读仓库+KB 做独立验证，退出码 `0=PASS 2=BLOCK 1=ERR`，发现写入 `minutes/`。
- **高风险时叠加第二异质血统复审**：另一飞毛腿再审一遍（hermes=DeepSeek、kimi=K2.7 血统不同，交叉把关）。`hermes` 可经 `bin/seat-hermes.sh <repo> review "" "$LOOP_REVIEW_PROVIDER" "$LOOP_REVIEW_MODEL"` 切指定 provider。codex 可达时也可作为额外异质验证。
- 读完整 `minutes/`，别只看 VERDICT 行——综合各座位意见 + 测试结果做裁决。

### 5. 裁决与迭代
- **PASS**（无 High/Critical 且测试过；高风险还需第二异质复审 PASS）→ 进收尾。
- **BLOCK** → 回 PLAN/ACT 修复。把"为什么挂、怎么改"写进 `KB/state.md`。
- 每轮末 `bin/checkpoint.sh <repo> "<本轮小结>"`：追加 state、提交代码检查点（`.roundtable/` 不进提交）、bump 轮次。

### 6. 停止条件（任一触发即停，交还人工）
- 验证 PASS（正常完成）。
- 轮次 ≥ `LOOP_MAX_ITERS`。
- 同一发现连挂 ≥ `LOOP_STUCK_LIMIT`（卡死探测——读 minutes 判断是否反复挂在同一处）。
- 无可用执行席（飞毛腿都不在）：自动模式直接 fail-fast 交还人工。
- token/时间超出你与用户约定的预算。

### 7. 收尾摘要（必给，人话）
向用户报告：
- **改了什么**：diff 概要（治 comprehension debt——别让用户对自己仓库失去理解）。
- **各座位裁决**：验证席（hermes/kimi/codex）说了什么，最终为什么 PASS 或为何停。
- **剩余风险 / 未决**：still-open 的问题。
- **下一步触发点**：要不要合分支、要不要再跑。

## 降级与安全
- **缺独立验证席**（飞毛腿都不在 + codex 不可达）→ 验证退化为你自查 + 提醒用户"少了独立验证，可信度下降"，不要假装验过；自动模式下空执行池会 fail-fast。
- **codex 当前多不可达**（chatgpt.com 后端 websocket tls）——属常态，reviewer 自动解析到飞毛腿即可，别硬等 codex。
- hermes 切 DeepSeek 报模型不存在 → 用 `hermes model` 确认实际 id，更新 `LOOP_REVIEW_MODEL`。
- 任何删除/覆盖/对外/花钱：停，向用户说清后果再确认，绝不在循环里无人值守地执行。
