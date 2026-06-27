# 圆桌提速设计草案 —— claude 退回纯脑 + 降级容错

> 状态：草案（待圆桌评审）
> 日期：2026-06-27
> 启发来源：Nous Research `hermes-agent` 的 Mixture of Agents（`agent/moa_loop.py`）
> 主诉：圆桌**慢**。不用 codex 的前提下，deepseek/kimi 都飞快，活儿本应很快。
> 范围决策（主人 2026-06-27）：本版**只让圆桌快速、稳定地完成「单个任务」**；并行执行（多任务分工）留到单任务跑稳后再拓展（见 §8）。

---

## 1. 背景与问题（带数据的诊断）

主人报告：圆桌慢到"我把文件一个个手动分发给各 agent 都比它快"。回查最近真实会议纪要，根因有三，全部有实证：

**根因 ①　claude 制度性揽 exec 活。**
`seat-claude.sh:42` 的 plan prompt 白纸黑字写着"握全上下文/改坏东西代价高的活**留给 claude**"。总指挥（claude）照章办事，每轮把核心执行派给自己。证据：评审会（session `20260627-130354`）本该只读 review，却生成了 `claude-exec.md` 14–18KB——claude 在执行。

**根因 ②　揽了还干不动。**
claude=Opus（最慢），headless 座位有 600s 硬超时（`run_seat`，`LOOP_SEAT_TIMEOUT`）。执行会（session `20260627-165609`）**全 5 轮 `claude-exec.md` 全是 0 字节**：啃不完→超时被杀→零产出，但 600s 的钟（和 token）一直在烧。同会 `hermes-exec.md` 4KB 有产出、`kimi-exec.md` 在评审会能干到 173KB——飞毛腿扛得动大活。

**根因 ③　exec 串行。**
`conductor.py:561` 是 `for p in plan:` 依次 `run_seat(...)`，每座位一个 subprocess。最慢的 claude 卡在队列里，把飞快的 deepseek/kimi 堵在后面。

**本版聚焦 ①②——提速的大头。** 数据：①② 让 claude 每轮空烧 600s（5 轮≈50 分钟纯空转），是数量级的浪费；③（串行）只在"一轮派 ≥2 个执行座位"时才咬人，且解决 ①② 后剩下的"多飞毛腿串行"只是几分钟的边际损耗。③ 的彻底解法是并行多任务执行，留到单任务跑稳后再拓展（§8）。

---

## 2. 目标与非目标

**目标（本版）：让圆桌快速、稳定地完成「单个任务」。**
- claude 退出执行 → 消除 Opus 在执行位上的 600s 超时空转（治 ①②）。
- 单座位超时/失败不再拖垮或阻断整轮（容错）。

**非目标（明确留给下一阶段，触发条件见 §8）**
- **并行多任务执行**（治 ③）——本版不做。等单任务能快速稳定完成后，再连同写冲突隔离一起拓展。
- MoA 式"便宜参谋档"（plan 阶段多脑视角聚合）。
- claude 独立"最终 synthesis 综合席"。
- git worktree 级写隔离。

---

## 3. MoA 启发：可迁移的技术点

读 `moa_loop.py` 源码，提炼四条；本版用前两条，后两条留待下一阶段。

| MoA 的做法（源码实证） | 迁移到圆桌 | 本版 |
|---|---|---|
| **只有 aggregator 动手**（带工具），reference 永不碰工具、只出视角 | claude 退回纯脑，手交给飞毛腿 | ✅ A |
| 单 reference 挂了记 `[failed]` 继续，**不 abort 整轮** | 单座位超时/失败记 note 继续 | ✅ B |
| reference 用 `ThreadPoolExecutor` 并行 fan-out，全部跑完才交 aggregator | exec 并行 fan-out | ⛔ 下一阶段（§8） |
| reference 拿剥过的精简上下文（省 ~8K token/次）、无工具 | 参谋席用精简上下文降 token | ⛔ 下一阶段 |

---

## 4. 设计：两件套

### A. claude 退回纯脑（彻底退出 exec）

主人决策：claude 只做 plan（指挥）+ 未来的 synthesis，**绝不进 exec 座位**。真要写大块核心代码，走"主持人带外亲写"特例（在主对话里、无超时——即 LESSONS 铁律 #6），不占圆桌执行位。

改动：
1. **`seat-claude.sh` plan prompt**：把"握全上下文/改坏东西代价高的活留给 claude"改为"执行一律优先派 deepseek(hermes)/kimi；claude 只指挥不执行"。
2. **`conductor.py` run() 派活过滤**（约行 557）：在 `plan = [p for p in plan if p["agent"] in seated]` 之后，追加过滤 `p["agent"] != commander`——代码层兜底，即使 plan 仍把活派给自己也被剔除。
3. **fallback 改向**（行 557 的 `or [...]`）：当过滤后 plan 为空，fallback 子任务不再给 `commander`，改派在座的飞毛腿（优先 kimi，其次 hermes；都不在座才回退 commander 并 log 警告）。

与铁律 #6 的关系：不冲突。铁律 #6 的"主持人亲写"本就是**带外通道**（主对话、无超时），与"圆桌内 claude 不进 exec 座位"是两件事。

### B. 单座位超时/失败不阻断整轮

`run_seat` 已"从不抛异常、用返回码区分"（超时 124 / 失败 1），进程组超时强杀也已就位——基础够。本版增量：

- 串行执行循环里，任一座位返回非 0 **不**中断后续座位、**不** abort 整轮（维持现状语义，本版把它确立为明确契约）。
- 把失败/超时的座位明确写一行进 `KB/state.md`（验证席 review 必读的共享黑板），形如 `⏱ kimi[exec] 超时 600s` / `✗ hermes[exec] rc=1`，**让验证席 review 时看得见**"这轮谁没干成"，据此裁决而非误判。
- 验证席裁决语义不变（PASS/BLOCK），只是多了"某座位失败"这一可见输入。

> 注：本版 exec **仍是串行**（不做并行）。B 是容错，不是并行。

---

## 5. 受影响文件

| 文件 | 改动 |
|---|---|
| `skills/loop-engine/bin/conductor.py` | run() 派活过滤 + fallback 改向（A）；失败座位写 `KB/state.md`（B） |
| `skills/loop-engine/bin/seat-claude.sh` | plan prompt 改"执行优先派飞毛腿"（A） |
| （新）冒烟/验证脚本 | 验证 claude 不再 exec、降级不崩（§6） |

不碰：座位 .sh 的 exec/review 主体、KB 桥、roundtable-memory（上一版冻结的中立记忆，本版零接触）、exec 循环的串行结构（并行留 §8）。

---

## 6. 验收标准

1. **claude 不再执行**：跑完一轮，`minutes/iter-*-claude-exec.md` 不再生成（或恒为空）；`claude-plan.md` 仍正常。
2. **变快**：同一任务，改前（claude 被派 exec → 600s 超时空转）vs 改后（飞毛腿接手），记录单任务墙钟；预期消除每轮的 600s 空转。
3. **不退化**：plan/review 流程、PASS/BLOCK/CAP 逻辑、checkpoint、归档（archive_to_memory）行为不变。
4. **降级不崩**：人为让一个执行座位超时/失败（如 `LOOP_SEAT_TIMEOUT=1`），整轮不崩、其余座位照常完成、review 能在 `KB/state.md` 看到失败 note。

验证方式：maker（主持人或被派座位）跑脚本、把结果写进黑板；checker（验证席）读结果裁决（守 maker≠checker，避开"验证席只读跑不了测试"的张力——见 LESSONS）。

---

## 7. 风险与取舍

**取舍：claude 完全退出 exec 的边界。**
若某任务确实需要 claude 写代码（大块核心引擎，铁律 #6），不进圆桌 exec，走主持人带外亲写。即"圆桌干常规分工活，claude 亲写干引擎活"，两条通道分明。

**取舍：本版接受"多飞毛腿串行"的边际损耗。**
A 之后若一轮派了 ≥2 个执行座位，它们仍串行（慢几分钟）。这是有意为之——相比 A 砍掉的 50 分钟空转，不值得为它引入并行写的冲突风险。等单任务跑稳，再统一上并行 + 写隔离（§8）。

> 上一版草案曾把"并行写"列为核心，并自带头号风险（两座位并行改同一文件互相覆盖）。本版按主人决策移除并行，**该风险随之从默认路径上消失**。

---

## 8. 下一阶段（明确触发条件）

**触发条件：当圆桌能快速、稳定地完成「单个任务」之后**，再拓展：

- **并行多任务执行**（治根因 ③）：exec 串行→`ThreadPoolExecutor` fan-out，收齐再串行汇报（躲 TextReporter 交错）；**必须连 git worktree 级写隔离一起做**，否则两座位并行改同一文件会冲突。
- **MoA 式便宜参谋档**：plan 阶段 deepseek/kimi 并行出便宜视角（精简上下文、无工具）→ claude 聚合成计划。
- **claude 独立"最终 synthesis"席**。
