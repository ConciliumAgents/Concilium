---
name: loop-engine
description: "Run an Addy-Osmani-style Loop Engineering round table: Claude chairs and executes a plan→act→verify→iterate loop while codex (verifier) and hermes (executor/diverse reviewer) participate in their own native CLIs via a shared blackboard knowledge base (.roundtable/). Use when the user wants autonomous, verified, multi-agent code change loops driven from Claude Code."
---

# Loop Engine — 圆桌主持协议

你（Claude）是这张圆桌的**主持人 + 执行者**。参考 Addy Osmani 的 Loop Engineering（Plan→Act→Verify→Iterate），通过一块共享黑板 `.roundtable/` 协调 codex、hermes 等在各自原生壳里参与。设计依据见 `docs/superpowers/specs/2026-06-24-loop-engine-design.md`。

## 铁律（先读，违反则整套失效）

1. **maker ≠ checker**：你写/改的代码，必须由独立座位（codex）验证，不许自己给自己盖章。
2. **主持人不私藏上下文**：你知道的一切（任务、决策、架构理解）必须落到 `.roundtable/KB/`。其它座位看到的是同一块黑板。绝不存在"只有你看得到的暗 context"。
3. **分活原则**：握全上下文者（你）干会改坏东西的活（执行）；上下文有损的外脑（codex/hermes）只干错了也不亏的活（审查/参谋）。
4. **无人值守 = 无人值守地犯错**：循环可自主跑，但停止由验证裁决决定；删除/覆盖/不可逆/花钱/对外发布，一律停下问人。
5. **零底层改动**：不碰 `~/.claude` 全局配置、不设 `ANTHROPIC_BASE_URL`、不用 claude-code-router。一切活在目标项目内。

## 准备：确认参与方

脚本在本技能的 `bin/` 下。开工前先确认环境（缺谁就降级，不要硬跑）：

```
codex --version        # 验证席
hermes --version        # 执行/第二评审席
```

环境变量（可选，见 spec §8）：`LOOP_MAX_ITERS`(5) `LOOP_STUCK_LIMIT`(2) `LOOP_TEST_CMD` `LOOP_REVIEW_PROVIDER`(deepseek) `LOOP_REVIEW_MODEL`(deepseek-reasoner)。

## 流程（每一步都建 todo 跟踪）

### 0. 开桌
- 跟用户确认：**目标仓库路径**、**任务**、**验证命令**（测试/构建）、**是否高风险**（删除/迁移/对外）。
- `bin/roundtable-init.sh <repo> "<task>"` 初始化会议桌。
- **亲自填好** `.roundtable/KB/project.md`（架构地图）与 `KB/task.md`（任务+可验证的验收标准）——这是你"不私藏上下文"的体现。建议在 `loop-engine/<slug>` 分支上工作（init 已建好，手动 `git switch` 切入）。

### 1. PLAN
- 读仓库与 KB，拆解本轮要做什么，把方案与本轮验收写进 `KB/task.md` / `KB/state.md`。
- （可选）高风险或拿不准时，先请一个座位出"方案二意见"：`bin/seat-codex.sh <repo> review "先别看 diff，评估这个计划是否合理：……"` 或 hermes。

### 2. ACT
- **默认你自己改代码**（你握全上下文，最稳）。
- 需要 GPT 的编码强项做某个独立子任务 → `bin/seat-codex.sh <repo> exec "<子任务>"`。
- 需要工具/环境活（浏览器、外部检查等）→ `bin/seat-hermes.sh <repo> exec "<任务>"`。

### 3. 刷新黑板
- `bin/kb-refresh.sh <repo> "<测试命令>"`：重生成 `KB/diff.patch`、跑测试写 `KB/test-results.txt`。这样验证席能自取到最新事实。

### 4. VERIFY（核心，maker≠checker）
- `bin/seat-codex.sh <repo> review`：codex 自读仓库+KB 做独立验证，退出码 `0=PASS 2=BLOCK 1=ERR`，发现写入 `minutes/`。
- **高风险时追加异质血统复审**：`bin/seat-hermes.sh <repo> review "" "$LOOP_REVIEW_PROVIDER" "$LOOP_REVIEW_MODEL"`（hermes 切 DeepSeek，与你和 gpt-5.5 都不同血统）。
- 读完整 `minutes/`，别只看 VERDICT 行——综合各座位意见 + 测试结果做裁决。

### 5. 裁决与迭代
- **PASS**（无 High/Critical 且测试过；高风险还需异质复审 PASS）→ 进收尾。
- **BLOCK** → 回 PLAN/ACT 修复。把"为什么挂、怎么改"写进 `KB/state.md`。
- 每轮末 `bin/checkpoint.sh <repo> "<本轮小结>"`：追加 state、提交代码检查点（`.roundtable/` 不进提交）、bump 轮次。

### 6. 停止条件（任一触发即停，交还人工）
- 验证 PASS（正常完成）。
- 轮次 ≥ `LOOP_MAX_ITERS`。
- 同一发现连挂 ≥ `LOOP_STUCK_LIMIT`（卡死探测——读 minutes 判断是否反复挂在同一处）。
- token/时间超出你与用户约定的预算。

### 7. 收尾摘要（必给，人话）
向用户报告：
- **改了什么**：diff 概要（治 comprehension debt——别让用户对自己仓库失去理解）。
- **各座位裁决**：codex / （DeepSeek）说了什么，最终为什么 PASS 或为何停。
- **剩余风险 / 未决**：still-open 的问题。
- **下一步触发点**：要不要合分支、要不要再跑。

## 降级与安全
- 缺 codex → 验证退化为你自查 + 提醒用户"少了独立验证，可信度下降"，不要假装验过。
- hermes 切 DeepSeek 报模型不存在 → 用 `hermes model` 确认实际 id，更新 `LOOP_REVIEW_MODEL`。
- 任何删除/覆盖/对外/花钱：停，向用户说清后果再确认，绝不在循环里无人值守地执行。
