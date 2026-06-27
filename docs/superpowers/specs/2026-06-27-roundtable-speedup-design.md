# 圆桌提速设计 v4 —— claude 退回纯脑 + 降级容错

> 状态：草案 v4（三轮异构评审收敛，准备进入实现）
> 日期：2026-06-27
> 启发来源：Nous Research `hermes-agent` 的 Mixture of Agents（`agent/moa_loop.py`）
> 主诉：圆桌**慢**。不用 codex 的前提下，deepseek/kimi 都飞快，活儿本应很快。
> 范围决策（主人）：本版**只让圆桌快速、稳定地完成「单个任务」**；并行执行留 §8。
> 评审历程：v1 双 BLOCK(1C+3H) → v2 hermes PASS/kimi BLOCK → v3 引入 executors 抽象 → v3 三轮 hermes PASS/kimi BLOCK(1C+3H，含 out-of-box 致命的默认 reviewer=codex) → v4 收敛。见 §9。

---

## 1. 背景与问题（带数据，三轮评审逐行核实）

- **① claude 制度性揽 exec 活**：`seat-claude.sh:42` / `seat-kimi.sh:80` 的 plan prompt 写"…活留给 claude"。证据：评审会 `20260627-130354` 生成 `claude-exec.md` 14–18KB。
- **② 揽了干不动**：claude=Opus(最慢)+600s 硬超时。执行会 `20260627-165609` **全 5 轮 `claude-exec.md` 全 0 字节**——超时空转，600s(含 token)白烧。
- **③ exec 串行**：`conductor.py:561` 的 `for p in plan:`。

本版聚焦 ①②(数量级浪费：50 分钟空转 vs 串行 3–9 分钟边际，10:1)；③ 留 §8。

---

## 2. 目标与非目标

**目标：让圆桌快速、稳定地完成「单个任务」。**
- claude 退出执行(消除 600s 空转)，改任**指挥 + 验证**(纯脑、只读、不超时)。
- 单座位超时/失败不阻断整轮(容错)。
- 不引入回归；圆桌 **out-of-box 可用**(默认配置不依赖坏掉的 codex)。

**非目标(留 §8)**：并行多任务；MoA 便宜参谋档；claude synthesis 席；git worktree 写隔离；roster 速度元数据驱动选座。

---

## 3. MoA 启发

| MoA 做法 | 迁移 | 本版 |
|---|---|---|
| 只有 aggregator 动手，reference 只出视角 | claude 退回纯脑，手交飞毛腿 | ✅ A |
| 单 reference 挂了记 note 继续，不 abort | 单座位失败不阻断整轮 | ✅ B |
| 并行 fan-out / 精简上下文降本 | exec 并行 / 参谋降本 | ⛔ §8 |

---

## 4. 设计

### A. claude 退回纯脑（退出 exec，转任指挥+验证）

**A0. 可执行座位集（executors）**——一处定义、处处一致：
```python
EXEC_EXCLUDE = {"claude", "codex"}   # 慢/不宜执行：claude=Opus 超时；codex=慢且连接坏
executors = [a for a in seated if a not in EXEC_EXCLUDE and a != reviewer]   # 飞毛腿执行池
```

**A1. plan prompt 改写（`seat-claude.sh` + `seat-kimi.sh`）**：
- `seat-claude.sh:42` / `seat-kimi.sh:80` 的旧原则**整句替换**为："执行一律优先派 hermes/kimi(飞毛腿)；claude、codex 只指挥/验证、不执行。"(只加不删会让 claude 继续自派高代价活、被过滤后触发无谓 fallback)
- `seat-claude.sh` 的**可用座位列表(行 41)、JSON 示例(行 47)、"agent 字段必须是 claude/codex/hermes 之一"(行 49)全部补上 kimi**——否则 claude 总指挥不知 kimi 可派，"优先 kimi"落空(v2/v3 反复确认的实现级漏洞)。

**A2. plan 过滤（基于 executors）+ 被过滤子任务记账**：
```python
kept = [p for p in plan if p["agent"] in executors]
dropped = [p for p in plan if p["agent"] not in executors]   # 派给 claude/codex/reviewer 的
plan = kept or _fallback_plan(executors, task, reason="filtered_empty")
```
- 每个 dropped 项 `reporter.log(...)` + **写入 `KB/state.md` 的 `## ⚠ 本轮被移出的子任务` 节 + 注入 review BRIEF**，让验证席知悉"这些活没人干"，据完整性裁决——**不静默丢弃**(修 v3-HIGH)。

**A3. 退化兜底 `_fallback_plan(executors, task, reason)`（区分原因）**：
- `executors` 非空 → 整个 task 派 `FAST_PRIORITY=["kimi","hermes"]` 中首个落在 executors 的座位。
  - `reason="filtered_empty"`：log "过滤后无可执行子任务，整活派飞毛腿 X"。
  - `reason="plan_failed"`(plan seat 失败/超时，B8)：同样派飞毛腿，**且**写 `## ⚠ 本轮总指挥失败` + 注入 BRIEF(让 reviewer 知道计划是兜底硬塞的)。
- `executors` 为空 → 见 A4 fail-fast(不回退 claude exec)。

**A4. reviewer 动态解析 + 空 executors fail-fast**（修 v3-CRITICAL 默认 reviewer=codex + v3-HIGH 空转）：
- **reviewer 解析**(取代 `--reviewer` 默认 "codex"，`conductor.py:601`)：
  1. 用户显式 `--reviewer` 且在座 → 用之；
  2. 否则**动态选**：在座飞毛腿(`seated ∩ ¬EXEC_EXCLUDE`) ≥2 → 选一个当**异质 reviewer**(优先 hermes，deepseek 血统利于复审)，其余进 executors；
  3. 在座飞毛腿恰 1 个 → 它进 executors 执行，**claude 兜底当 reviewer**(纯脑只读，仍满足 maker≠checker：maker=飞毛腿、checker=claude，且 claude 不 exec)；
  4. 在座飞毛腿 0 个 → **fail-fast**：写 `KB/conclusion.md` 说明"无可用执行座位"，`reporter.log("⚠ 无飞毛腿在座，圆桌需≥1 飞毛腿；纯 claude 请走主对话带外亲写")`，直接 return CAP(**不进迭代循环空烧**)。
- **maker≠checker 警告调整**(`conductor.py:537`)：`commander==reviewer` 仅当该座位**会 exec**(∉ EXEC_EXCLUDE)时才告警；claude 既 commander 又 reviewer 且不 exec 时**不告警**(maker=飞毛腿独立)。

### B. 单座位超时/失败不阻断整轮

`run_seat` 已"从不抛异常、返回码区分"(超时 124/失败 1)+进程组强杀；串行 exec 循环本就无 `break`。本版确立契约 + 补可见性：

- **B5. 失败写 `KB/state.md`**：exec loop 内、review 之前；**追加**到固定节 `## ⚠ 本轮座位失败`(座位自身也写 state.md，conductor 只追加；多座位失败 loop 内收集后一次写入)。格式 `⏱ kimi[exec] 超时 600s` / `✗ hermes[exec] rc=1`。
- **B6. 统一构建 review BRIEF**：新增 `build_brief(failures, dropped, plan_failed)` 显式构建器，汇总「失败座位 + 被移出子任务 + 完整性裁决前缀」，**注入 review**(`run_seat(reviewer,"review",repo,brief=...)`；当前行 575 未传)。约定：BRIEF 有上限、与上一轮 `feedback`(行 587)分节拼接防膨胀、空则不传。
- **B7. 完整性裁决规则落到 seat review prompt**(不只 BRIEF，修 v3-HIGH)：在 `seat-claude.sh` / `seat-kimi.sh` / `seat-hermes.sh` 的 **review 段 prompt** 加一句固定指令："若 BRIEF 标明有座位失败/子任务未执行，请据**任务完整性是否受损**裁决；某座位失败但任务已由其余座位完成时不应机械 BLOCK。"
- **B8. plan 阶段失败并入 A3**(`reason="plan_failed"`)：plan seat 失败/超时 → 走 A3 兜底 + 写 state.md + 注入 BRIEF。

> 本版 exec **仍串行**；B 是容错非并行。reviewer 自身失败仍判 ERR 结束整轮(正确)。

### C. 必修回归：记忆归档路径〔CRITICAL〕

`_archive_lessons`(`conductor.py:413`)glob 改 `iter-*-claude-exec.md` → **`iter-*-*-exec.md`**(抽所有座位 exec 纪要的 `## 教训`；只匹配 `-exec.md`，不误抽 plan/review；SHA-256 去重仍生效)。`_archive_result` 不受影响。**同步更新** `archive_to_memory`(行 320)/`_archive_lessons`(行 407)的 docstring 去掉"claude-exec/综合席"字样。

### D. 一致性周边

`roster-detect.py`(行 39–69)把 codex 标 `modes=["exec","review"]`、特长"强编码"——与 EXEC_EXCLUDE 矛盾，会误导花名册/TUI。改为 codex 仅 `["review"]`(或标注不宜 exec)，与 A0 一致。

---

## 5. 受影响文件

| 文件 | 改动 |
|---|---|
| `conductor.py` | executors(A0)、过滤+dropped记账(A2)、`_fallback_plan`(A3)、reviewer 动态解析+fail-fast+告警调整(A4)、B5/B6/B8、C(glob+docstring) |
| `seat-claude.sh` | plan prompt 整句替换 + 可用座位/示例/允许值补 kimi(A1)；review 段加完整性规则(B7) |
| `seat-kimi.sh` | plan prompt 整句替换(A1)；review 段加完整性规则(B7) |
| `seat-hermes.sh` | review 段加完整性规则(B7) |
| `roster-detect.py` | codex 标记与 EXEC_EXCLUDE 一致(D) |
| (新)冒烟/验证脚本 | §6 |

不碰：座位 exec 主体、KB 桥、roundtable-memory 数据、exec 循环串行结构(§8)。

---

## 6. 验收标准

1. **claude 不再执行**：跑完一轮 `iter-*-claude-exec.md` 不生成；claude 出现在 plan 与(兜底时)review。
2. **out-of-box 可用(CRITICAL 验收)**：不传 `--reviewer`，默认配置(claude+hermes+kimi 在座、codex 不在座)能跑通整轮，reviewer 自动解析为飞毛腿，不触 codex。
3. **变快**：同任务改前/后墙钟，消除每轮 600s 空转。
4. **归档不断流(CRITICAL 验收)**：一轮 PASS 后 kimi/hermes 的 exec `## 教训` 能进 LESSONS.md。
5. **过滤不误伤 + maker≠checker**：`--commander=kimi` 时 kimi 的 exec 子任务不被过滤；reviewer 不被派 exec；被过滤子任务出现在 state.md + BRIEF。
6. **kimi 可被派活**：默认 `--commander=claude` 下 claude 能把 exec 派给 kimi(seat-claude.sh 已含 kimi)。
7. **空 executors fail-fast**：仅 claude 在座(无飞毛腿)→ 第一轮即 return CAP + 明确报错，不空烧 max_iters，不产生 claude-exec。
8. **降级不崩**：制造 exec 座位失败(**注意** `LOOP_SEAT_TIMEOUT=1` 会连 plan 超时，须只对 exec 注入失败或 mock 单座位 rc≠0)；整轮不崩、其余完成、review 在 state.md 和 BRIEF 都见 note。

验证：maker 跑脚本写结果进黑板，checker 读结果裁决(守 maker≠checker)。

---

## 7. 风险与取舍

- **异质复审优先，claude 兜底**：飞毛腿≥2 时 reviewer 用异质飞毛腿(保住异质复审价值——三轮评审已证其重要)；仅 1 飞毛腿时 claude 兜底 reviewer，**同血统、有确认偏见**(审自己 plan 的实现易宽)，属可接受的降级；0 飞毛腿 fail-fast。
- **planner=doer 接受**：`--commander=hermes/kimi` 时该飞毛腿既 plan 又可 exec(不违 maker≠checker，因 checker=独立 reviewer)。本版接受，不禁止。
- **全降级圆桌不执行**：无飞毛腿在座 → fail-fast 交还人工；纯 claude 单座位本就该走主对话带外亲写。
- **有效执行席常仅 1 个**：claude 退出 + 一个飞毛腿当 reviewer → executors 常剩 1，恰印证本版"单任务"足够(并行无意义)，呼应范围决策。
- **claude 退出 exec 的边界**：大块核心引擎(铁律 #6)走主持人带外亲写。
- **飞毛腿快慢取决于绑定模型**：`FAST_PRIORITY` 硬编码(当前 hermes=deepseek、kimi=K2.7 均快)；roster 速度标签留 §8。

---

## 8. 下一阶段（触发：单任务能快速稳定完成后）

并行多任务(治 ③)+ git worktree 写隔离；MoA 便宜参谋档；roster 速度元数据驱动选座；claude 独立 synthesis 席。

---

## 9. 圆桌评审账

- **一轮(v1→v2)**：双 BLOCK。CRITICAL 归档断流；HIGH 过滤硬编码/fallback 缺校验/退化路径。
- **二轮(v2→v3)**：hermes PASS / kimi BLOCK。引入 executors 统一抽象，消 fallback 误派 reviewer、A3/A4 冲突、codex 一致、seat-claude 缺 kimi。
- **三轮(v3→v4)**：hermes PASS / kimi BLOCK。本轮收敛：

| kimi 三轮发现 | 级别 | v4 处理 |
|---|---|---|
| 默认 `--reviewer=codex`，out-of-box ERR | CRITICAL | §4-A4 reviewer 动态解析(不再 codex) |
| 空 executors 不 fail-fast，空烧 max_iters | HIGH | §4-A4 fail-fast 第一轮即停 |
| 被过滤 plan 子任务静默丢弃 | HIGH | §4-A2 dropped 记账 + BRIEF |
| B7 完整性规则只在 BRIEF、未进 seat prompt | HIGH | §4-B7 落到 seat review prompt |
| B8 并入 A3 丢诊断、未分原因 | MEDIUM | §4-A3 reason 区分 + plan_failed 记账 |
| seat-claude 旧原则须整句替换、允许值含 kimi | MEDIUM | §4-A1 整句替换 + 行 41/47/49 |
| commander 可同时 executor | MEDIUM | §7 声明接受 |
| reviewer 占唯一飞毛腿致 executors 空、文案误导 | MEDIUM | §4-A4 区分(claude 兜底而非误报"无飞毛腿") |
| state.md/BRIEF 注入机制未定义 | MEDIUM | §4-B6 build_brief 构建器 |
| roster-detect 仍标 codex exec | MEDIUM | §4-D 一致 |
| 归档可能混入非标准占位 | LOW | 实现时 `_lesson_items` 已跳过占位，足够 |

hermes 三轮 PASS(确认 executors 抽象消解 v2 矛盾)。本版收敛后转入实现，剩余实现级细节(BRIEF 格式上限、文案)在编码 + 审真代码阶段就地处理。
