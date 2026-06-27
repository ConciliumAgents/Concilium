# 圆桌提速设计草案 v2 —— claude 退回纯脑 + 降级容错

> 状态：草案 v2（已据圆桌轻量评审收敛；hermes(deepseek)+kimi 异构评审 v1 → 双 BLOCK）
> 日期：2026-06-27
> 启发来源：Nous Research `hermes-agent` 的 Mixture of Agents（`agent/moa_loop.py`）
> 主诉：圆桌**慢**。不用 codex 的前提下，deepseek/kimi 都飞快，活儿本应很快。
> 范围决策（主人 2026-06-27）：本版**只让圆桌快速、稳定地完成「单个任务」**；并行执行（多任务分工）留到单任务跑稳后再拓展（见 §8）。
> v2 变更：修 1 CRITICAL（归档路径退化）+ 3 HIGH（过滤硬编码假设 / fallback 缺在座校验 / 退化路径）+ 多 MEDIUM。见 §4 标注与 §9 评审账。

---

## 1. 背景与问题（带数据的诊断，评审已逐行核实）

主人报告：圆桌慢到"我把文件一个个手动分发给各 agent 都比它快"。回查最近真实会议纪要，根因有三，全部有实证（两位异构评审席逐行对照源码确认无误）：

**根因 ①　claude 制度性揽 exec 活。** `seat-claude.sh:42`（及 `seat-kimi.sh:80`）的 plan prompt 白纸黑字写着"握全上下文/改坏东西代价高的活**留给 claude**"。总指挥照章办事，每轮把核心执行派给自己。证据：评审会（session `20260627-130354`）本该只读 review，却生成了 `claude-exec.md` 14–18KB。

**根因 ②　揽了还干不动。** claude=Opus（最慢），headless 座位有 600s 硬超时（`run_seat`，`LOOP_SEAT_TIMEOUT`）。执行会（session `20260627-165609`）**全 5 轮 `claude-exec.md` 全是 0 字节**：啃不完→超时被杀→零产出，但 600s 的钟（和 token）一直在烧。同会 `hermes-exec.md` 4KB 有产出、`kimi-exec.md` 在评审会能干到 173KB。

**根因 ③　exec 串行。** `conductor.py:561` 是 `for p in plan:` 依次 `run_seat(...)`。

**本版聚焦 ①②（提速大头）。** 数据：①② 让 claude 每轮空烧 600s（5 轮≈50 分钟纯空转）；③（串行）解决 ①② 后只剩"多飞毛腿串行"的 3–9 分钟边际损耗（评审确认 10:1 量级差，取舍合理）。③ 的彻底解法是并行多任务，留 §8。

---

## 2. 目标与非目标

**目标（本版）：让圆桌快速、稳定地完成「单个任务」。**
- claude 退出执行 → 消除 Opus 在执行位上的 600s 超时空转（治 ①②）。
- 单座位超时/失败不再拖垮或阻断整轮（容错）。
- **不引入回归**：尤其上一版的中立记忆飞轮（归档/召回）必须继续工作。

**非目标（留下一阶段，触发见 §8）**：并行多任务执行；MoA 式"便宜参谋档"；claude 独立 synthesis 席；git worktree 写隔离；roster 速度/成本元数据驱动选座。

---

## 3. MoA 启发：可迁移的技术点

| MoA 的做法（源码实证） | 迁移到圆桌 | 本版 |
|---|---|---|
| **只有 aggregator 动手**（带工具），reference 永不碰工具、只出视角 | claude 退回纯脑，手交给飞毛腿 | ✅ A |
| 单 reference 挂了记 `[failed]` 继续，**不 abort 整轮** | 单座位超时/失败记 note 继续 | ✅ B |
| reference 并行 fan-out / 精简上下文降 token | exec 并行 / 参谋席降本 | ⛔ §8 |

---

## 4. 设计：两件套 + 一处必修回归

### A. claude 退回纯脑（彻底退出 exec）

claude 只做 plan（指挥），**绝不进 exec 座位**。真要写大块核心代码，走"主持人带外亲写"特例（主对话、无超时——LESSONS 铁律 #6），不占圆桌执行位。

1. **plan prompt 正面引导（`seat-claude.sh` 和 `seat-kimi.sh` 都改）**〔修 MEDIUM·kimi〕
   把"…留给 claude"改为：**"执行一律优先派 hermes/kimi（飞毛腿）；claude、codex 这类慢座位只指挥不执行。"** 两个 plan 座位脚本同步改（否则换 kimi 当 commander 时计划仍违策）。

2. **conductor 过滤：按"不宜执行集合"而非无条件排除 commander**〔修 HIGH·两家共识〕
   v1 的 `p["agent"] != commander` 隐含假设 commander 永远是慢的 claude；若 `--commander=kimi` 会把最快座位误踢。改为维护一个显式集合：
   ```python
   EXEC_EXCLUDE = {"claude"}   # 慢/不宜执行的座位；可扩展（如未来纳入 codex）
   plan = [p for p in plan if p["agent"] in seated and p["agent"] not in EXEC_EXCLUDE] or _fallback_plan(...)
   ```
   过滤掉某项时 `reporter.log(...)`（审计可见，修 LOW·hermes#3）。

3. **fallback 从实际在座挑飞毛腿**〔修 HIGH·两家共识〕
   ```python
   FAST_PRIORITY = ["kimi", "hermes"]
   fast = next((a for a in FAST_PRIORITY if a in seated and a not in EXEC_EXCLUDE), None)
   ```
   挑到 → fallback 子任务派它；挑不到（飞毛腿都不在座）→ 回退 commander + `reporter.log("⚠ 无飞毛腿在座，回退 commander，可能超时")`（透明回归，见 §7）。**不**硬编码派给不在座的 agent。

4. **退化路径：过滤后无可执行 exec 子任务**〔修 HIGH·kimi〕
   若过滤后 plan 仅剩 reviewer 的验证类子任务、或为空且无飞毛腿可派 → 不静默空转：写一行进 `KB/state.md`（`## ⚠ 本轮无可执行 exec 座位/子任务`）+ 注入 review BRIEF，让验证席据实裁决，而非面对"无改动"瞎猜。

### B. 单座位超时/失败不阻断整轮

`run_seat` 已"从不抛异常、用返回码区分"（超时 124 / 失败 1）+ 进程组强杀就位；串行 exec 循环本就无 `break`（评审确认现状即不 abort）。本版把它**确立为契约**并补可见性，要点：

5. **失败写 `KB/state.md` 的时序与方式**〔修 MEDIUM·hermes#5 + kimi〕
   - **时序**：在 **exec loop 内、review 之前**写（`checkpoint.sh` 在 review 之后执行，来不及）。
   - **追加不覆盖**：座位自身 prompt 已要求写 state.md，conductor 用**追加**，固定小节 `## ⚠ 本轮座位失败` + 稳定行格式 `⏱ kimi[exec] 超时 600s` / `✗ hermes[exec] rc=1`，便于 review 稳定解析。

6. **双通道把失败摘要喂给验证席**〔修 MEDIUM·hermes#6〕
   LLM 不保证读 state.md。除写 state.md 外，把失败摘要**注入 review 的 BRIEF**（`run_seat(reviewer,"review",repo,brief=失败摘要)`，preamble 的 `${BRIEF:+额外关注…}` 通道已预留）。两条通道都落。

7. **验证席裁决规则（写进 BRIEF 措辞）**〔修 MEDIUM·kimi〕
   失败 note 是 reviewer 的**输入之一**，应据"**任务完整性是否受损**"判断 PASS/BLOCK，**不机械 BLOCK**（某座位失败但任务已由其余座位完成时可 PASS）。

8. **plan 阶段 commander 失败也记一行**〔延伸·kimi〕plan 的 `run_seat` 失败/超时同样写 state.md，避免后续基于残缺计划执行却无痕。

> 注：本版 exec **仍串行**；B 是容错，不是并行。reviewer 自身失败仍按现状判 ERR 并结束整轮（正确，不纳入"不阻断"）。

### C. 必修回归：记忆归档路径〔修 CRITICAL·kimi〕

`_archive_lessons`（`conductor.py:413`）硬编码 `glob("iter-*-claude-exec.md")`。**claude 退出 exec 后该 glob 永远空 → LESSONS.md 再也吸不到执行轮教训 = 上一版刚建的记忆飞轮被掐断。**

修复（一行）：glob 改为 **`iter-*-*-exec.md`**——抽**所有座位** exec 纪要的 `## 教训` 节。`seat-kimi.sh`/`seat-hermes.sh` 的 exec prompt 已要求写 `## 教训`（数据源现成）。
- `_archive_result`（PASS 成果落叶子）**不依赖** claude-exec，不受影响（已核实）。
- 这条与 A 同生死：A 落地必须连带改 C，否则隐性功能退化。

---

## 5. 受影响文件

| 文件 | 改动 |
|---|---|
| `skills/loop-engine/bin/conductor.py` | EXEC_EXCLUDE 过滤 + fallback 挑在座飞毛腿 + 退化路径（A2/3/4）；失败写 state.md（exec 内、追加）+ 注入 review BRIEF（B5/6/7/8）；`_archive_lessons` glob 改 `iter-*-*-exec.md`（C） |
| `skills/loop-engine/bin/seat-claude.sh` | plan prompt 正面引导（A1） |
| `skills/loop-engine/bin/seat-kimi.sh` | plan prompt 同步改（A1） |
| （新）冒烟/验证脚本 | §6 验收 |

不碰：座位 exec/review 主体、KB 桥、roundtable-memory 数据、exec 循环的串行结构（并行留 §8）。

---

## 6. 验收标准

1. **claude 不再执行**：跑完一轮，`iter-*-claude-exec.md` 不再生成（或恒空）；`claude-plan.md` 仍正常。
2. **变快**：同一任务，改前（claude 被派 exec→600s 空转）vs 改后（飞毛腿接手）墙钟对比，消除每轮 600s 空转。
3. **不退化**：plan/review、PASS/BLOCK/CAP、checkpoint、`_archive_result` 行为不变。
4. **归档不退化（CRITICAL 验收）**：一轮 PASS 后，kimi/hermes 的 exec 纪要里的 `## 教训` 能被 `_archive_lessons` 抽进 LESSONS.md（即 claude 不 exec 也不断流）。
5. **过滤不误伤（HIGH 验收）**：`--commander=kimi` 时，kimi 的 exec 子任务**不**被过滤（EXEC_EXCLUDE 只含 claude）。
6. **降级不崩**：人为制造 exec 座位失败（**注意**：`LOOP_SEAT_TIMEOUT=1` 会连 plan 一起超时——验收脚本须只对 exec 阶段注入失败，或 mock 单座位 rc≠0，特别构造）〔两家 LOW〕；整轮不崩、其余座位完成、review 在 state.md **和** BRIEF 都看到失败 note。

验证方式：maker 跑脚本写结果进黑板，checker 读结果裁决（守 maker≠checker，避"验证席只读跑不了测试"张力——见 LESSONS）。

---

## 7. 风险与取舍

- **全降级仍回 claude exec**（A3）：飞毛腿都不在座时回退 commander=claude，可能超时——合法但被接受的回归路径，带 log 透明；B 的非阻断可兜住。
- **claude 完全退出 exec 的边界**：大块核心引擎（铁律 #6）走主持人带外亲写，不进圆桌 exec。两条通道分明。
- **飞毛腿快慢取决于其绑定模型**〔hermes#2/kimi〕：本版用硬编码集合 `FAST_PRIORITY`，未读 roster 速度元数据。可接受（当前 hermes=deepseek、kimi=K2.7 均快）；roster 速度标签驱动选座留 §8。
- **验证席裁决靠 LLM 判断"完整性"**（B7）：给了规则但非强约束，属可接受的软指导。
- **接受"多飞毛腿串行"的边际损耗**：相比 A 砍掉的 50 分钟空转不值一提；并行 + 写隔离留 §8。

---

## 8. 下一阶段（触发条件：单任务能快速稳定完成后）

- 并行多任务执行（治根因 ③）+ **必须连 git worktree 写隔离**；ThreadPool fan-out、收齐再串行汇报（躲 TextReporter 交错）。
- MoA 式便宜参谋档（plan 阶段多脑视角聚合，精简上下文降本）。
- roster 速度/成本元数据驱动选座（取代 FAST_PRIORITY 硬编码）。
- claude 独立"最终 synthesis"席。

---

## 9. 圆桌评审账（v1 → v2）

hermes(deepseek) + kimi 各自逐行读源码独立评审 v1，双 VERDICT: BLOCK。收敛如下：

| 严重度 | 发现 | v2 处理 |
|---|---|---|
| CRITICAL | `_archive_lessons` 硬编码 claude-exec，claude 退出后归档断流 | §4-C：glob 改 `iter-*-*-exec.md` |
| HIGH | 过滤 `!=commander` 假设 commander=慢 claude，换 kimi 会误伤 | §4-A2：EXEC_EXCLUDE 集合 |
| HIGH | fallback 硬编码顺序，未校验在座/`--seats` | §4-A3：从 seated 挑 |
| HIGH | 过滤后只剩 reviewer 验证活 → exec 零执行空转 | §4-A4：退化路径 |
| MEDIUM | seat-kimi.sh plan prompt 也含"留给 claude" | §4-A1：同步改 |
| MEDIUM | state.md 写入时序（须 review 前）+ 追加不覆盖 | §4-B5 |
| MEDIUM | review 不保证读 state.md | §4-B6：注入 BRIEF |
| MEDIUM | 验证席见失败如何裁决无规则 | §4-B7：完整性规则 |
| MEDIUM | 只驱逐 claude 不够，codex 也慢 | §4-A1：prompt 正面引导优先飞毛腿 |
| LOW | 过滤/fallback 无审计日志 | §4-A2/A3：加 reporter.log |
| LOW | `LOOP_SEAT_TIMEOUT=1` 会连 plan 超时 | §6-6：验收特别构造 |
| LOW | 飞毛腿模型速度未知 | §7 + §8：roster 元数据留未来 |
