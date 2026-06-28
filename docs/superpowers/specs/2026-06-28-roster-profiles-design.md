# 座位画像设计草案 —— 给主持人派活一份「实战依据」

> 状态：草案（待圆桌轻审）
> 日期：2026-06-28
> 起因（用户洞察）：圆桌设计让主持人(claude)分活+把控会议，但**主持人派活的唯一依据是 `roster.md` 的静态 `strength`**——那是 `roster-detect.py` 硬编码的"出厂标称"，**粗**（一句话特长）且**会失真**（标 codex"强编码"实则连不上、标 claude 适合"核心活"实则揽 exec 超时）。主持人需要对每个模型的**实战了解**才有依据派活。

---

## 1. 问题

派活依据链现状：`roster-detect.py` 探测座位 → 每座位一个静态 `strength` → `write_roster()` 写 `KB/roster.md` → 主持人 plan 时"读 roster.md，按特长派活"。

缺口：`strength` 是出厂标称，不反映实战。真正有用的画像（谁快谁慢、谁严谁松、谁血统异质、谁有坑）这次才挖出来，却散落在对话/LESSONS，主持人开会读不到。

---

## 2. 目标与非目标

**目标**：给主持人一份**可读、可积累的座位实战画像**作为派活/选席依据。
- 主持人 plan 时能读到每座位的实战特长、适合角色、坑。
- 画像随每场圆桌持续积累。

**非目标（留后续）**：
- 自动画像生成（从纪要自动提炼）——MVP 先手动维护。
- 画像驱动的自动派活（仍由主持人 LLM 据画像判断，不做硬规则引擎）。

---

## 3. 方案

### 3.1 载体：`roundtable-memory/ROSTER-PROFILES.md`

- 放 `roundtable-memory/`（**进 git**、纯 markdown、**中立**——任何 agent 可读，与 INDEX.md/LESSONS.md 并列，成为 roundtable-memory 第三成员）。
- 每座位一节，固定维度：

```markdown
## <seat> (<模型>, <血统>)
- 出厂特长：<roster-detect 的 strength，留作对照>
- 实战画像：<速度 / 性格 / 真实表现，基于会议实测>
- 适合角色：<plan / exec / review / 异质复审 …>
- 坑：<已知的失效模式 / 注意事项>
```

### 3.2 接线：合并进 `roster.md`（不走记忆桥、无开关、零回归）

**关键决策**：画像**不**走 roundtable-memory 的 `_roundtable_memory()` 召回——那套受 `LOOP_USE_ROUNDTABLE_MEMORY`（默认关）控制，默认关时主持人读不到。改为：

- `write_roster()`（`conductor.py`）在写 `KB/roster.md` 时，**额外读 `roundtable-memory/ROSTER-PROFILES.md`**，按座位名匹配，把"实战画像/适合/坑"并进该座位在 roster.md 的节里（出厂层 + 实战层两层并列）。
- 主持人 plan 本就"读 KB/roster.md"（prompt 已有），**无需新召回机制、无需开关、无零回归顾虑**。
- 读 PROFILES 失败（文件不存在/格式坏）→ 跳过，roster.md 退化为纯出厂层（向后兼容）。

### 3.3 初始画像（从本轮实战 + 历史整理）

- **claude (Opus, Anthropic)**：出厂=编排/规划/综合、长上下文；实战=握全上下文强，但揽 exec 会 600s 超时空转；适合=总指挥(plan)+验证席(review，纯脑只读)；坑=**不可进 exec 座位**，大块核心代码走主对话带外亲写。
- **hermes (DeepSeek, 异质)**：出厂=工具/环境广度；实战=执行快有产出，复审**偏宽松**（"修复成立"即放行）；适合=执行席、异质复审（综合时需 kimi 交叉验证）；坑=复审易放过深层边界。
- **kimi (K2.7, Moonshot, 异质)**：出厂=异质评审/强编码；实战=**深挖边界最狠**（三轮评审次次中）、快、能扛大活（单纪要 173KB）；适合=严格验证席、核心执行、异质复审；坑=headless 输出冗长（thinking 外泄）、无超时会跑很久（曾 11 分钟）。
- **codex (GPT, OpenAI)**：出厂=代码验证/强编码；实战=chatgpt.com 后端 `websocket tls handshake eof`，**当前连不上、不可用**；适合=（暂无，已入 EXEC_EXCLUDE 只验证）；坑=连接坏，别派活。

### 3.4 积累流程（MVP 手动）

- 谁写：散会后由主持人（或人工）把本场新观察到的实战表现，更新进对应座位节。
- 纪律：同 LESSONS——新增前先看该座位已有画像，有则合并/更新，勿堆叠矛盾；保持精炼。
- 后续可半自动（从 minutes 提炼），留下一阶段。

### 3.5 迁移：LESSONS 那条画像归位 PROFILES

`LESSONS.md` 通用铁律里刚加的"主持人派活须基于实战画像（claude退exec/hermes宽松/kimi深挖）"——**画像部分迁入 PROFILES**（一处真相），LESSONS 只留**原则**那句（"派活须基于实战画像而非静态 strength + 审真代码>审spec"），不重复列具体画像。

---

## 4. 受影响文件

| 文件 | 改动 |
|---|---|
| `roundtable-memory/ROSTER-PROFILES.md` | 新建，四座位初始画像（§3.3） |
| `conductor.py` `write_roster()` | 读 PROFILES 并按座位合并进 roster.md（§3.2），失败跳过 |
| `roundtable-memory/LESSONS.md` | 画像具体内容迁出，只留原则（§3.5） |

不碰：roster-detect.py（出厂层不变）、记忆桥/召回开关、座位脚本。

---

## 5. 验收标准

1. `KB/roster.md` 每座位节同时含"出厂特长 + 实战画像/适合/坑"。
2. 主持人 plan 能据画像派活（如不把 exec 派给 claude、严审优先 kimi）——观察一轮 plan 输出。
3. **零回归**：`ROSTER-PROFILES.md` 不存在/格式坏时，`write_roster` 不崩，roster.md 退化为纯出厂层。
4. 画像不依赖 `LOOP_USE_ROUNDTABLE_MEMORY` 开关（默认即生效）。
5. LESSONS 不再重复列具体画像（只留原则），PROFILES 为画像唯一真相。

---

## 6. 风险与取舍

- **画像主观 + 样本少**：当前每座位仅 1–2 次实战。MVP 接受"少而真"，随会议积累；不强求全面。
- **更新纪律靠人**：MVP 手动更新，可能滞后/遗漏。可接受（比没有强）；半自动留后续。
- **roster.md 变长**：每座位多几行。无害（主持人本就读它）。
- **画像可能固化偏见**：把某次表现当永久标签（如"hermes 宽松"或许只是某次）。缓解：画像写"倾向"而非"绝对"，并随新证据更新。

---

## 7. 下一阶段

- 半自动画像：散会从 minutes 提炼表现，提示主持人确认后更新。
- 画像维度细化（按任务类型分：写代码 vs 评审 vs 调研）。
