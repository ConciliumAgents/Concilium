# 圆桌提速设计 v3 —— claude 退回纯脑 + 降级容错

> 状态：草案 v3（两轮异构评审收敛）
> 日期：2026-06-27
> 启发来源：Nous Research `hermes-agent` 的 Mixture of Agents（`agent/moa_loop.py`）
> 主诉：圆桌**慢**。不用 codex 的前提下，deepseek/kimi 都飞快，活儿本应很快。
> 范围决策（主人 2026-06-27）：本版**只让圆桌快速、稳定地完成「单个任务」**；并行执行留到单任务跑稳后（见 §8）。
> 评审历程：v1 → 双 BLOCK（1C+3H）；v2 → hermes PASS / kimi BLOCK（深挖出"主修复半失效"等真问题）；v3 用统一抽象收敛。见 §9。

---

## 1. 背景与问题（带数据，两轮评审逐行核实）

主人报告：圆桌慢到"我把文件一个个手动分发给各 agent 都比它快"。根因三条，均有实证：

- **① claude 制度性揽 exec 活**：`seat-claude.sh:42` / `seat-kimi.sh:80` 的 plan prompt 写"…活**留给 claude**"。证据：评审会 `20260627-130354` 生成 `claude-exec.md` 14–18KB。
- **② 揽了干不动**：claude=Opus（最慢）+ 600s 硬超时。执行会 `20260627-165609` **全 5 轮 `claude-exec.md` 全 0 字节**——超时空转，600s（含 token）白烧。
- **③ exec 串行**：`conductor.py:561` 的 `for p in plan:`。

**本版聚焦 ①②（数量级浪费：50 分钟空转 vs 串行的 3–9 分钟边际，评审确认 10:1）；③ 留 §8。**

---

## 2. 目标与非目标

**目标：让圆桌快速、稳定地完成「单个任务」。**
- claude 退出执行 → 消除 600s 超时空转（治 ①②）。
- 单座位超时/失败不阻断整轮（容错）。
- 不引入回归（尤其上一版的中立记忆飞轮必须继续工作）。

**非目标（留 §8）**：并行多任务；MoA 便宜参谋档；claude synthesis 席；git worktree 写隔离；roster 速度元数据驱动选座。

---

## 3. MoA 启发

| MoA 做法（源码实证） | 迁移 | 本版 |
|---|---|---|
| 只有 aggregator 动手，reference 不碰工具只出视角 | claude 退回纯脑，手交飞毛腿 | ✅ A |
| 单 reference 挂了记 note 继续，不 abort | 单座位失败不阻断整轮 | ✅ B |
| 并行 fan-out / 精简上下文降本 | exec 并行 / 参谋降本 | ⛔ §8 |

---

## 4. 设计：核心抽象「可执行座位集」+ 两件套 + 一处必修回归

### A. claude 退回纯脑 —— 基于「可执行座位集」统一建模

v1/v2 评审反复在过滤、fallback、reviewer、codex、退化路径上发现边界矛盾。根因是这些规则各写各的。v3 用**一个**概念统一：

**A0. 可执行座位集（executors）**〔统一消解 v2 的 HIGH/MEDIUM 群〕
```python
EXEC_EXCLUDE = {"claude", "codex"}   # 慢/不宜执行：claude=Opus 超时；codex=慢且当前连接坏
# 可执行座位 = 在座 ∩ 非慢座位 ∩ 非验证席（maker≠checker 内建：reviewer 永不 exec）
executors = [a for a in seated if a not in EXEC_EXCLUDE and a != reviewer]
```
plan 过滤与 fallback 全部基于 `executors`，一处定义、处处一致。

**A1. plan prompt 改写（`seat-claude.sh` + `seat-kimi.sh` 都改）**〔修 kimi：主修复半失效〕
1. "…活留给 claude" → **"执行一律优先派 hermes/kimi（飞毛腿）；claude、codex 只指挥/验证、不执行。"**
2. **`seat-claude.sh` 的"可用座位"列表与 JSON 示例必须补上 `kimi`**（现仅列 claude/codex/hermes，行 41/49）。否则 claude 总指挥不知道 kimi 可派，"优先 kimi"落空——这是 v2 的实现级漏洞。

**A2. plan 过滤（基于 executors）**〔修 HIGH① + reviewer 排除 + codex 一致〕
```python
plan = [p for p in plan if p["agent"] in executors] or _fallback_plan(executors, task, reviewer)
```
过滤掉任一项时 `reporter.log(...)`（审计可见）。换 `--commander=kimi` 不会误伤 kimi（kimi ∉ EXEC_EXCLUDE）；claude/codex/reviewer 的 exec 子任务一律被剔除。

**A3. 退化兜底 `_fallback_plan`（统一 v2 的 A3/A4，消歧）**〔修 kimi：A3/A4 冲突 + plan 失败 + 回退矛盾〕
过滤后 plan 为空（原 plan 全派给了 claude/codex/reviewer，或 plan 阶段本身失败返回空）时：
- **executors 非空** → 整个 task 派给 `FAST_PRIORITY=["kimi","hermes"]` 中第一个落在 executors 的座位；`reporter.log("过滤后无可执行子任务，整活派飞毛腿 X")`。
- **executors 为空**（全降级，无飞毛腿在座）→ **不回退 claude exec**（忠于"彻底退出"）。改为：写 `KB/state.md` 固定节 `## ⚠ 本轮无可执行座位` + 注入 review BRIEF，让验证席据实裁决（大概率 BLOCK，交还人工）；`reporter.log("⚠ 无飞毛腿在座，本轮不执行；圆桌至少需 1 个飞毛腿，纯 claude 请走主对话带外亲写")`。

> 此决策取代 v2 §7 的"回退 commander(claude)"——那条与"claude 绝不 exec"自相矛盾（kimi 指出）。v3 选择：宁可不执行 + 提示人工，也不让 claude 回去空转。

### B. 单座位超时/失败不阻断整轮

`run_seat` 已"从不抛异常、返回码区分"（超时 124 / 失败 1）+ 进程组强杀；串行 exec 循环本就无 `break`（现状即不 abort）。本版确立契约 + 补可见性：

- **B5. 失败写 `KB/state.md`**：在 **exec loop 内、review 之前**写（`checkpoint.sh:15` 在 review 之后，来不及）；**追加**到固定节 `## ⚠ 本轮座位失败`（座位自身也写 state.md，conductor 只追加不覆盖；多座位失败在 loop 内收集后一次写入，避免重复 header）。格式 `⏱ kimi[exec] 超时 600s` / `✗ hermes[exec] rc=1`。
- **B6. 双通道喂验证席**：除写 state.md 外，把失败摘要**注入 review 的 BRIEF**（`run_seat(reviewer,"review",repo,brief=摘要)`；当前 `conductor.py:575` 未传 brief，各 review prompt 的 `${BRIEF:+…}` 通道已就绪）。空摘要时不传，避免虚假关注。
- **B7. 验证席裁决规则（写进 review BRIEF 前缀，不只内容）**〔修 kimi：软约束需落地〕：BRIEF 前缀明确"以下失败 note 是输入之一，请据**任务完整性是否受损**判 PASS/BLOCK，某座位失败但任务已由其余座位完成时不应机械 BLOCK"。
- **B8. plan 阶段失败并入 A3**：plan 的 `run_seat` 失败/超时 → plan 为空 → 走 A3（优先飞毛腿、**不**回退 claude）+ 写 state.md + 注入 BRIEF。

> 本版 exec **仍串行**；B 是容错非并行。reviewer 自身失败仍按现状判 ERR 结束整轮（正确，不纳入"不阻断"）。

### C. 必修回归：记忆归档路径〔修 CRITICAL〕

`_archive_lessons`（`conductor.py:413`）硬编码 `glob("iter-*-claude-exec.md")`。claude 退出 exec 后该 glob 恒空 → LESSONS.md 断流。
修复：glob 改 **`iter-*-*-exec.md`**（抽所有座位 exec 纪要的 `## 教训`；kimi/hermes exec prompt 已要求写该节，数据源现成；只匹配 `-exec.md`，不误抽 plan/review；SHA-256 去重仍生效，已两轮核实）。`_archive_result` 不受影响。**同步更新** `archive_to_memory`（行 320）与 `_archive_lessons`（行 407）的 docstring/注释（去掉"claude-exec/综合席"字样）。

---

## 5. 受影响文件

| 文件 | 改动 |
|---|---|
| `conductor.py` | executors 抽象 + A2 过滤 + `_fallback_plan`（A3）；B5 写 state.md + B6 注入 review BRIEF + B7 前缀 + B8；C：glob 改 + docstring 同步 |
| `seat-claude.sh` | plan prompt 改写 + **可用座位列表/JSON 示例补 kimi**（A1） |
| `seat-kimi.sh` | plan prompt 同步改（A1） |
| （新）冒烟/验证脚本 | §6 |

不碰：座位 exec/review 主体、KB 桥、roundtable-memory 数据、exec 循环串行结构（§8）。

---

## 6. 验收标准

1. **claude 不再执行**：跑完一轮，`iter-*-claude-exec.md` 不再生成；`claude-plan.md` 正常。（全降级也不回退 claude，故无例外）
2. **变快**：同一任务改前/改后墙钟，消除每轮 600s 空转。
3. **不退化**：plan/review、PASS/BLOCK/CAP、checkpoint、`_archive_result` 不变。
4. **归档不断流（CRITICAL 验收）**：一轮 PASS 后，kimi/hermes 的 exec `## 教训` 能被 `_archive_lessons` 抽进 LESSONS.md。
5. **过滤不误伤 + maker≠checker（HIGH 验收）**：`--commander=kimi` 时 kimi 的 exec 子任务不被过滤；`--reviewer=kimi` 时 kimi **不**被 fallback 派去 exec。
6. **kimi 可被派活（HIGH 验收）**：默认 `--commander=claude` 下，claude 的 plan 能把 exec 子任务派给 kimi（验证 seat-claude.sh 已含 kimi）。
7. **降级不崩**：制造 exec 座位失败（**注意** `LOOP_SEAT_TIMEOUT=1` 会连 plan 一起超时，验收脚本须只对 exec 注入失败或 mock 单座位 rc≠0）；整轮不崩、其余座位完成、review 在 state.md **和** BRIEF 都见失败 note。
8. **全降级行为**：仅 claude 在座（无飞毛腿）时，本轮不执行、写 `## ⚠ 本轮无可执行座位`、review 据实、log 提示人工——不产生 claude-exec。

验证：maker 跑脚本写结果进黑板，checker 读结果裁决（守 maker≠checker，避"验证席只读跑不了测试"张力）。

---

## 7. 风险与取舍

- **全降级时圆桌不执行**（A3）：无飞毛腿在座 → 明确不执行、交还人工，而非让 claude 空转。这是有意决策（忠于"彻底退出"），代价是"纯 claude 圆桌"不可用——但纯 claude 单座位本就该走主对话带外亲写，不该用圆桌。
- **有效执行座位常仅 1 个**：当前座位池 claude/hermes/kimi（codex 坏），claude 被排除、一个飞毛腿当 reviewer → executors 往往只剩 1 个。这恰好印证本版"单任务"足够（单执行座位，并行无意义），呼应范围决策；多飞毛腿并行留 §8。
- **claude 退出 exec 的边界**：大块核心引擎（铁律 #6）走主持人带外亲写，不进圆桌 exec。
- **飞毛腿快慢取决于绑定模型**：本版 `FAST_PRIORITY` 硬编码（当前 hermes=deepseek、kimi=K2.7 均快）；roster 速度标签驱动选座留 §8。
- **B7 完整性裁决靠 prompt**：软指导（已落到 BRIEF 前缀），非强规则引擎，属可接受限制。

---

## 8. 下一阶段（触发：单任务能快速稳定完成后）

- 并行多任务执行（治 ③）+ **必须连 git worktree 写隔离**；ThreadPool fan-out、收齐再串行汇报。
- MoA 便宜参谋档（plan 多脑视角聚合，精简上下文降本）。
- roster 速度/成本元数据驱动选座（取代 FAST_PRIORITY/EXEC_EXCLUDE 硬编码）。
- claude 独立 synthesis 席。

---

## 9. 圆桌评审账

**第一轮（v1，hermes+kimi 双 BLOCK）→ v2**：CRITICAL 归档断流（§4-C）；HIGH 过滤硬编码（→EXEC_EXCLUDE）、fallback 缺校验（→从 seated 挑）、退化路径（→A4）；多 MEDIUM。

**第二轮（v2，hermes PASS / kimi BLOCK）→ v3**：

| kimi 二轮发现 | 严重度 | v3 处理 |
|---|---|---|
| `seat-claude.sh` 可用座位/示例无 kimi，主修复半失效 | HIGH | §4-A1.2 补 kimi |
| fallback 未排除 reviewer，破 maker≠checker | HIGH | §4-A0 executors 内建排除 reviewer |
| A3/A4 优先级冲突 + "回退 claude"自相矛盾 | HIGH | §4-A3 统一 `_fallback_plan`，全降级不回退 claude |
| A1 说 codex 不执行但 EXEC_EXCLUDE 只含 claude | MEDIUM | §4-A0 EXEC_EXCLUDE 纳入 codex |
| B7 完整性规则仅靠 BRIEF 内容、易被机械 BLOCK | MEDIUM | §4-B7 写进 BRIEF 前缀 |
| plan 失败后回退 commander 会让 claude exec | MEDIUM | §4-B8 并入 A3，不回退 claude |
| docstring/注释未随 glob 改 | LOW | §4-C 同步 |

hermes 二轮 PASS（确认各修复成立），唯一建议（A3/A4 补句消歧）已被 v3 的统一 `_fallback_plan` 吸收。
