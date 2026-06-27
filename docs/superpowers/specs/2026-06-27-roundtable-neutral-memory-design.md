# 圆桌中立持久记忆（roundtable-memory）— 设计文档（spec）

- 日期：2026-06-27
- 状态：设计草案 v2（圆桌审议 PASS + 主人补充"教训库/防膨胀"后定稿，待主人 review）
- 作者：Claude Code（拉姆，综合席/单写者）+ melee
- 圆桌会话：`20260627-122306-任务-为-loop-engine-圆桌设计一套-`
- 证人：hermes（DeepSeek，exec 自证）/ kimi（Moonshot，评审席补答）→ **两证人均已确认中立，见 §9.1**
- 红线：本文档**只设计、不落地**——不改圆桌任何现有代码、不真建 `roundtable-memory/` 目录。

---

## 0. 综合席诚实声明（缺口与其闭合）

本会要求两个异质证人（hermes、kimi）**各自亲答**第 1 条"中立性自证"，互为交叉验证。过程与闭合状态如实记录：

- ✅ **hermes（DeepSeek）exec 阶段亲答**：`minutes/iter-1-hermes-exec.md`，完整覆盖 #1–#4。
- ⚠️→✅ **kimi（Moonshot K2.7）exec 阶段缺席**：本轮总指挥 plan 派活时未给 kimi 分配 exec 子任务，故 exec 阶段无 `iter-1-kimi-exec.md`。**kimi 的中立性自证由其在评审席（review）阶段补答**（`minutes/iter-1-kimi-review.md`），实质缺口已闭合，本 v2 已将其证言回写进 §9.1 证人 B。

**诚实标注**：kimi 的自证是"评审席补答"而非"独立 exec 亲答"，严格意义上交叉验证的独立性略弱于双 exec。这条本身已记入 §9.2 风险表与教训库候选（见 §6 示例）：**总指挥派活必须覆盖每个"该自证/该发言"的座位**。

> 本会铁律（task.md【红线】）：缺口 = 重读 / 明说，绝不脑补。前几轮综合席曾在工具结果异常时幻觉出不存在内容并空转，本会不重蹈。

---

## 1. 结论（一句话）

为 loop-engine 圆桌建一个**自己的、进 git、任何 agent 都能独立读取**的持久记忆 `roundtable-memory/`：**档案馆定位**（写一次、只读归档，非活台账），落在 **repo 根**（git 版本化）。它含**两类知识、各有其家**：

1. **成果库** `<project>/<topic>.md` —— PASS 定稿成果，按项目→主题组织，`INDEX.md` 索引。
2. **教训库** `LESSONS.md` —— 失败/协作教训，**通用核心 + 分项目**两区，用来让协作**越跑越稳**。

写入靠 conductor 散会时在 `write_conclusion()` 后加一步 **`archive_to_memory()`（纯 Python、指挥进程内跑、不调用任何座位 → 天然 agent 无关）**；召回靠 **记忆桥 `import_memory()` 改以本库为主源**（既有的 Claude 私库、散落 conclusion 降为补充/兜底），并对教训库做**分层召回防膨胀**（§6.3）。格式刻意**只用标准 markdown**（标准链接、无 `[[]]`、无 frontmatter、无 `/→-` 路径映射），保证非-Claude 座位零打折读取（两证人已确认）。

---

## 2. 背景与问题（为什么开这会）

### 2.1 现状的死结

圆桌成果现存于 **gitignored** 的 `.roundtable/sessions/<id>/KB/conclusion.md`（`.gitignore` 第 2 行 `.roundtable/` 把整棵树排除）。两个致命后果：

1. **不进 git**：换机器 / 重新 clone 即全丢，成果没有持久落点。
2. **召回只走 Claude 体系**：记忆桥 `conductor.import_memory()`（`conductor.py:171`）汇集的三源里，主体是 **Claude 私库** `~/.claude/projects/<repo /→- 映射>/memory/*.md` + gitignored 散落 conclusion。hermes / kimi **读不到 Claude 私库**，只能靠记忆桥转述。

**实锤（非推断）**：本会话 `KB/imported-memory.md` 实际构成 = 6 份 `## Claude 项目记忆`（私库）+ 7 份 `## 过往会话结论`（gitignored conclusion）。**两类来源没有一个**是 git 版本化、agent 中立的。

→ 圆桌实质沦为 **"Claude 的延展工具"**——其他 agent 一旦离开圆桌就读不到任何成果。本会打破这个死结。

### 2.2 目标与红线

- **目标**：给圆桌一个进 git、agent 无关、任何 agent 独立可读的持久记忆，且**能积累教训、自我改进、又不随时间膨胀**。
- **红线**：本会**只产设计文档**，不改现有代码、不真建目录、缺口标"待补"绝不编造。

---

## 3. 定位：档案馆型 MVP

| 维度 | 决策 | 理由 |
|---|---|---|
| 性质 | **档案馆**（写一次、只读归档） | 存定稿成果 + 提炼后的教训，不是随时改写的活台账 |
| 复杂度 | **先 MVP 能 work，不过度工程** | 明确**砍掉** amazon-fba 那套防漂移机械守卫 / 不变式 / L1 绝对规则层 |
| 写入触发 | conductor 散会自动归档（§7） | agent 无关、零人工 |
| **归档门槛** | **PASS → 成果库**；**任何会的 `## 教训` 节 → 教训库** | 成果只收定稿；教训不分成败都收（失败教训尤其值钱） |
| 召回 | 成果按需 + **教训分层防膨胀**（§6.3 / §8） | recall 命令、开局 hook 属后续非 MVP |

---

## 4. 位置：repo 根 `roundtable-memory/`，进 git

```
<repo>/
├── .roundtable/                 # gitignored → 会话过程态，会丢
│   └── sessions/<id>/KB/conclusion.md
└── roundtable-memory/           # ★新增，git 版本化 → 持久，不丢
    ├── README.md                # 冷启动说明（§11.4）
    ├── INDEX.md                 # 成果库索引：项目→主题两级
    ├── LESSONS.md               # ★教训库：通用铁律 + 分项目教训（§6）
    ├── agents/<topic>.md        # 成果叶子
    ├── amazon-fba/<topic>.md
    ├── finance/<topic>.md
    └── _meta/<topic>.md         # 跨项目 / 圆桌自身议题
    # （后续非 MVP）LESSONS-archive/  老教训滚动归档，不参与召回
```

**为什么在 repo 根、绝不放 `.roundtable/` 下**：`.roundtable/` 被 gitignore，放进去等于继续丢。

**gitignore 实证**：当前 `.gitignore` = `.venv/` / `.roundtable/` / `__pycache__/` / `*.pyc` / `*.png` / `.playwright-mcp/`——**无一条匹配 `roundtable-memory/`**，故默认被追踪。（防未来误伤见 §9.2-R6。）

---

## 5. 成果库结构：INDEX + 叶子（三层砍 L1 的极简版）

参考 amazon-fba 三层记忆，**砍掉 L1 绝对规则层**，只留：

- **L2 索引 `INDEX.md`**：按 **项目 → 主题** 两级。每条一行：`[显示名](相对路径) — YYYY-MM-DD · 一句话状态/结论`。
- **L3 叶子 `<project>/<topic>.md`**：该议题历次圆桌定稿成果，固定分节（议题 / 结论 / 关键决策 / 源指针 / 历次更新）。

**项目划分**：`agents` / `amazon-fba` / `finance`；跨项目或圆桌自身议题归 `_meta/`。`<project>` 是**项目名**，非 `/→-` 路径映射产物 → Claude 这条隐含假设不传染到新设计。模板见 §11。

---

## 6. 教训库 `LESSONS.md`（主人补充 · 让协作越跑越稳）

### 6.1 为什么要它

失败教训不是垃圾，是另一种成果：一次会为什么 BLOCK、卡在哪、验证席揪出什么致命问题，正是"下次别再犯"的金子。成果库只收 PASS 定稿，会把这些教训丢掉。`LESSONS.md` 收容它们，并通过**召回时主动喂给座位**，形成"每次的坑下次自动带上"的改进飞轮。（先例：amazon-fba 的 CLAUDE.md 专设"幻觉事件复盘机制"，"记教训"是被验证过的好做法。）

### 6.2 结构：两区

```markdown
# 圆桌教训库（LESSONS）

## 通用铁律（每次开会全量置顶召回 · 刻意保持小而收敛）
- 工具结果异常/有缺口时，重读或明说，**绝不脑补**填补。（源：注入攻击幻觉空转事件）
- 综合席"已修"摘要的每一条，正文必须真有；改完自 grep 核对。（源：摘要↔正文断层）
- 总指挥派活必须覆盖每个"该自证/该发言"的座位，否则关键发言缺席。（源：本设计会 kimi exec 缺席）
- participants 以"实际在座"为准，勿据硬编码默认派活给已下桌座位。（源：座位漂移 bug）

## 分项目教训（开会只召回当前项目这一节）
### agents
- （示例）……
### amazon-fba
- （尚无）
### finance
- （尚无）
```

- **通用核心**：协作机制层面、跨项目通用的教训。**小而收敛**——靠"毕业"机制（§6.3-③）保持不膨胀。
- **分项目**：与具体项目绑定的教训，按项目分节。

### 6.3 防膨胀三招（直接回应"全量读会越来越大"）

| 招 | 治什么 | 做法 | MVP？ |
|---|---|---|---|
| ① 存精炼不存原始 | 单条体积 | 每条一行：教训 + 怎么避 + 一个源指针；原始留 conclusion | ✅ MVP |
| ② 分层召回 | "读"的膨胀 | 召回 = `通用铁律`（全量，因其小）+ **仅当前项目**那节；不读他项目、不读原始纪要（§8.2） | ✅ MVP |
| ③ 教训"毕业" | "写"的膨胀（根治） | 同类反复出现→合并进通用铁律（去重不重复增）；过时标 `SUPERSEDED`；量大→老条目滚动进 `LESSONS-archive/`（不召回） | ⚠️ 部分：去重/SUPERSEDED 靠**写入纪律**（MVP）；自动合并 + 滚动归档（后续） |

**诚实边界**：③ 的去重收敛靠**会议写 `## 教训` 时的纪律**（先查通用铁律有无同类，有则强化/合并而非新增），非自动魔法。这与主人 CLAUDE.md §5"迭代不累积"一致。①② MVP 直接落，保证召回量不随历史总量线性增长。

---

## 7. 写入设计：`archive_to_memory()`（纯 Python · agent 无关）

### 7.1 插入点（真实行号锚点）

`conductor.py` 的 `run()` 收尾（`conductor.py:336-339`）：

```python
status = status or "CAP"
write_conclusion(repo, task, status, final_it, verdicts)   # :337
reporter.finish(status, final_it)
return {"PASS": 0, "ERR": 1, "CAP": 2}[status]
```

设计：在 `write_conclusion(...)` **之后**、`reporter.finish(...)` 之前插一行 `archive_to_memory(...)`。**本会不落地**（红线）。

### 7.2 为什么"天然 agent 无关"

`archive_to_memory()` 是 `conductor.py` 里的**纯 Python 函数**，在**指挥进程自身**执行（与 `write_conclusion` / `import_memory` 同层），**不经 `run_seat()` 调用任何座位 agent、不依赖任何 agent 工具链或私库**。无论在座是谁，归档行为一致。

### 7.3 职责（设计草案 — 仅描述，不落地）

```python
def archive_to_memory(repo, task, status, rounds, verdicts) -> None:
    """散会归档：成果落成果叶子、教训落 LESSONS.md，均 git 版本化。
    纯标准库、指挥进程内执行、不调用任何座位 agent。"""
    # 【成果】仅 status == "PASS" 才归档（档案馆 = 定稿成果）：
    #   ① 定 project（默认取圆桌所在 repo 对应项目名；跨项目→ _meta/，主持人显式指定）
    #   ② 定 topic slug：复用 conductor 既有 _slug()（conductor.py:120）。⚠ _slug 保留 CJK，
    #      叶子文件名可能含中文 → 落地时提供 ASCII fallback 或 README 注明编码约定（§9.2-R15）
    #   ③ leaf = roundtable-memory/<project>/<topic>.md：不存在→按 §11.2 模板建；
    #      已存在→刷新「结论/关键决策」、「历次更新」表 append 一行（append-only）
    #   ④ 先写叶子、成功后再更新 INDEX.md 对应行（顺序见 §9.2-R5）
    # 【教训】不分成败：若本会任一座位纪要含 `## 教训` 小节（minutes/*.md）：
    #   ⑤ 机械抽取该小节文本，按"项目/通用"append 到 LESSONS.md 对应区（§6.2）
    #      —— 只搬运，不"理解"；提炼由会议当场写纪要时完成（§6.3 诚实边界）
    # ⑥ 全程 try/except、失败不抛（与 write_conclusion 同样 OSError 容错）
```

### 7.4 与 `write_conclusion` 的分界（去重，采纳 hermes 风险 #7）

| | `write_conclusion()` →`.roundtable/.../conclusion.md`（gitignored） | `archive_to_memory()` → `roundtable-memory/`（git） |
|---|---|---|
| 内容 | 单次会话**完整记录**：任务原文、各轮裁决、diffstat、checkpoint、minutes 清单 | **定稿成果摘要** + **提炼后的教训** |
| 性质 | 审计轨迹（过程态，可丢） | 知识积累（成果态，进 git） |
| 关系 | 不删、保留；作教训/成果的"源指针"溯源目标 | 新增 |

---

## 8. 召回设计（MVP 两条路径，含分层防膨胀）

### 8.1 路径一：进 git → 谁 clone 谁被动可读（零机制依赖）

任何 agent clone 仓库后，直接读 `roundtable-memory/INDEX.md` / `LESSONS.md` → 顺标准 markdown 链接读叶子。**不需要记忆桥、不需要 Claude 私库、不需要任何 agent 专属解析**。这一条就让 hermes / kimi 脱离圆桌也拿得到——打破 §2 死结的根本一招。

### 8.2 路径二：记忆桥 `import_memory()` 改造（开会路径上真读 + 分层防膨胀）

现状 `import_memory()`（`conductor.py:171-196`）三源：① 仓库 CLAUDE.md ② Claude 私库（`/→-`，非 Claude 读不到）③ gitignored 散落 conclusion。

**设计改造（仅描述，不落地）**：

1. **成果库为主源**：若 `INDEX.md` 存在，将其 + 各叶子标题摘要作为新增节 `## 圆桌持久记忆` 附入 `imported-memory.md`。因其进 git、中立，列**主源**。
2. **教训库分层召回（防膨胀核心）**：
   - 读 `LESSONS.md` 的 `## 通用铁律` **全量**（小、通用，置顶喂所有座位）；
   - 仅读 `## 分项目教训` 下**当前项目（按 repo 对应项目名匹配）**那一节；
   - **不读**其他项目的教训、**不读**原始纪要。→ 召回量随"通用铁律 + 本项目教训"涨，不随历史总量线性膨胀。
   - （增强，可选）再按 task 关键词在本项目节内 grep 高相关条目优先。
3. **既有源降级（修原 v1 措辞矛盾）**：源 ②（Claude 私库）、源 ③（散落 conclusion）**降为补充/兜底**——仅加载主源未覆盖的，**并非整体替换**。`imported-memory.md` 标注每节来源，去重避免混淆。

> 〔后续非 MVP，本会不做：独立 `recall` 命令、各 agent 开局 hook 自动召回、`LESSONS-archive/` 自动滚动。〕

---

## 9. 中立性自证 + 风险缓解

### 9.1 第 1 条 · 中立性自证（两证人均已确认）

#### 证人 A：hermes（DeepSeek）— exec 亲答 ✅

> 来源：`minutes/iter-1-hermes-exec.md`，已实读 KB 全 7 文件、`conductor.py` 全 361 行、两份 conclusion、现有 spec、`.gitignore`。

**结论：能读到、能读懂、能用上。唯一打折点是 `[[]]` 指针，有替代写法。** 其工具链 `read_file`/ripgrep 无 wiki-link 解析、无 frontmatter schema、无 `/→-` 概念。

#### 证人 B：kimi（Moonshot K2.7）— 评审席补答 ✅

> 来源：`minutes/iter-1-kimi-review.md`（exec 缺席，review 补答，见 §0）。

**结论（kimi 原话要点）**："该格式我能独立读到、读懂、用上，无需 Claude 专属能力。" 逐项：纯 markdown + 标准链接 `Read` 直接读、可继续读目标文件，**无需额外约定**；两级 INDEX 可用 Glob/Grep 检索；`[[]]` 无内置解析→**弃用正确**；frontmatter 能读但不结构化解析→**弃用正确**；`/→-` 用项目名→对它无隐含假设；固定分节按 `## ` 切分即可解析，**Moonshot 侧无兼容问题**（原 R13"Moonshot 专属打折点"= 无）。

#### 双证人共识 → 写进格式铁律

1. **链接一律标准 markdown**：`[显示名](agents/topic.md)`、叶子间 `[文本](../agents/other.md)`。**全程禁用 `[[]]`**。
2. **不用 frontmatter**：元数据放叶子标题下 key-value 列表。
3. **不依赖 `/→-` 映射**：`<project>` 用项目名。
4. **源指针路径基准**（修原 v1 LOW 歧义）：源指针**以仓库根为基准**书写（如 `.roundtable/sessions/<id>/KB/conclusion.md` 即指仓库根下该路径），模板顶部显式声明此约定；如需严格相对叶子位置则写 `../../.roundtable/...`。

### 9.2 第 2 条 · 风险缓解表

整合 hermes（R1–R10）、综合席源码读出（R11–R12）、kimi 评审补充（R13 闭合、R14 路径约定、R15 中文文件名）、主人补充（R16 膨胀）。

| # | 风险 | 严重度 | 缓解 | 来源 |
|---|---|---|---|---|
| R1 | 并发写 INDEX/LESSONS 冲突 | 低（MVP 单用户串行、conductor 单进程） | MVP 依赖串行前提；后续加 `fcntl.flock` 或临时文件 + 原子 `rename` | hermes |
| R2 | 叶子命名碰撞（同项目同 slug） | 中 | 写前查存在；存在且内容不同→追加 `-2` 或拒写报错；INDEX 含 slug，冲突可见 | hermes |
| R3 | 跨项目归类歧义 | 中 | 默认归圆桌所在 repo 项目；`_meta/` 仅显式跨项目；叶子内 `项目` 字段注明 | hermes |
| R4 | 与记忆桥/conclusion 衔接去重 | 中 | 以本库为主源，私库/conclusion 降补充（§8.2）；标注每节来源 | hermes |
| R5 | archive 失败回滚（叶子↔INDEX 不一致） | 中 | **先写叶子、后更 INDEX**；叶子失败则整体放弃；INDEX 失败叶子无害（可扫描重建）。不搞两阶段提交 | hermes |
| R6 | gitignore 未来误伤 | 低 | `.gitignore` 加注释 `# roundtable-memory/ 勿 ignore`；或放 `.gitkeep` | hermes |
| R7 | conclusion↔archive 语义重叠 | 低 | §7.4 分界：conclusion=完整审计；叶子=定稿摘要 | hermes |
| R8 | INDEX 损坏无法自动重建 | 低 | MVP 靠 git 回滚；后续 `rebuild-index.sh` 扫叶子重建 | hermes |
| R9 | conductor 崩溃致归档中断 | 低 | conclusion 仍在本地磁盘，下轮 import 仍读到；后续加"扫未归档"恢复 | hermes |
| R10 | 人改叶子 vs 下次归档覆盖 | 低 | MVP：archive 只写不读已有；人工修改应作下一轮圆桌输入 | hermes |
| R11 | 归档门槛 | 中 | **成果仅 PASS 归档；教训不分成败归档**（§3）。BLOCK/CAP 完整轨迹仍在 conclusion，不丢失 | 综合席+kimi |
| R12 | 同 topic 重复归档合并策略 | 中 | 刷新「结论/关键决策」+「历次更新」append 一行（保留轨迹、不搞版本树） | 综合席 |
| R13 | Moonshot 侧专属打折点 | — | **kimi 评审确认：无**（标准 markdown 对其零打折） | kimi ✅闭合 |
| R14 | 源指针相对路径基准歧义 | 低 | 模板声明"以仓库根为基准"（§9.1-4） | kimi |
| R15 | `_slug()` 保留 CJK→文件名含中文 | 低 | 落地提供 ASCII fallback 或 README 注明编码约定 | kimi |
| R16 | **教训库随时间膨胀，全量召回成本失控** | **中** | **§6.3 三招**：存精炼 + 分层召回（通用铁律全量、仅本项目节）+ 教训"毕业"去重/SUPERSEDED/滚动归档 | **主人** |

### 9.3 第 3 条 · MVP 范围（增删）

- **该砍**：hermes/kimi 均评"无"——当前 MVP 已极简；重申已砍 fba 防漂移守卫/不变式/L1。
- **该加（MVP 必需易漏）**：① `README.md` 冷启动说明；② `import_memory()` 改读（否则建了不读=白建）；③ `.gitignore` 防误伤注释；④ **教训库 `LESSONS.md` + 分层召回**（主人补充，§6）。

---

## 10. 实施清单（供后续落地 — 本会不执行）

> 红线：本会**只产文档**。以下为将来落地的最小动作，**本轮一律不做**。

1. 真建 `roundtable-memory/`：`INDEX.md` + `LESSONS.md` + `README.md` + 各项目空目录（`.gitkeep`）。
2. `conductor.py` 加 `archive_to_memory()`，在 `:337` 后调用一行（成果叶子 + 教训抽取）。
3. `conductor.py` 改 `import_memory()`：本库为主源、教训分层召回、私库/conclusion 降补充。
4. `.gitignore` 加防误伤注释。
5. （后续非 MVP）`rebuild-index.sh`、未归档恢复工具、`LESSONS-archive/` 滚动、recall 命令、开局 hook、`_slug` ASCII fallback。

**待补**：第 2/3 步具体改动量与优先级需 owner（melee）确认。

---

## 11. 最小可用格式（模板）

> 要求：**人类可读 + 各 agent 可解析 + 不依赖 Claude 专属语法**（两证人确认）。

### 11.1 `INDEX.md`（成果库索引）

```markdown
# 圆桌记忆索引（INDEX）

> 两级：项目 → 主题。每行：[显示名](相对路径) — YYYY-MM-DD · 一句话状态/结论
> 链接：相对本目录的标准 markdown 链接（禁用 [[]]）。
> 更新：每次圆桌散会由 archive_to_memory() 自动追加/更新；人类亦可手编。

## agents
- [loop-engine 圆桌架构](agents/loop-engine-roundtable.md) — 2026-06-24 · 黑板架构圆桌（已实现验证）
- [Kimi 迁移方案](agents/kimi-migration-plan.md) — 2026-06-27 · 三项目→Kimi 承接（PLAN v5，圆桌4轮 PASS，仅方案）

## amazon-fba
- （尚无归档）

## finance
- （尚无归档）

## _meta
- [圆桌中立记忆设计](_meta/roundtable-neutral-memory-design.md) — 2026-06-27 · 本系统的设计决策与格式约定
```

### 11.2 叶子 `<topic>.md`（成果）

```markdown
# 议题标题（人类可读一句话）

- **日期**：2026-06-27
- **项目**：agents
- **圆桌会话**：20260627-122306-...
- **状态**：定稿 / 草稿 / 已推翻
- **关联议题**：[Kimi 迁移方案](../agents/kimi-migration-plan.md)

## 议题
（要解决什么、为什么开会——1-3 段）

## 结论
（最终结论——最重要，agent 召回优先读这里）

## 关键决策
- 决策 1：……（理由：……）

## 源指针
> 路径以仓库根为基准
- KB 结论：`.roundtable/sessions/<id>/KB/conclusion.md`
- 座位发言：`.roundtable/sessions/<id>/minutes/`
- 产出文件：`docs/.../<deliverable>.md`

## 历次更新
| 日期 | 圆桌会话 | 变更摘要 |
|------|---------|---------|
| 2026-06-27 | 20260627-122306 | 初始定稿 |
```

### 11.3 `LESSONS.md`（教训库）

见 §6.2 结构示例。要点：`## 通用铁律`（全量召回、小而收敛）+ `## 分项目教训`（按项目分节、只召回当前项目）；每条一行含源指针；去重/SUPERSEDED 靠写入纪律。

### 11.4 `README.md`（冷启动说明）

```markdown
# 圆桌持久记忆（档案馆）

loop-engine 圆桌的 **git 版本化持久记忆**。任何 agent 读本目录即可独立获取圆桌历史，无需特定 agent 的私用记忆系统。

- `INDEX.md` — 成果索引（项目→主题），每行指向一个叶子
- `<project>/<topic>.md` — 叶子：该议题定稿成果
- `LESSONS.md` — 教训库：通用铁律 + 分项目教训（开会时召回，让协作越跑越稳）

链接一律标准 markdown（无 [[]]、无 frontmatter）。
```

---

## 12. 待补清单

| 项 | 性质 | 谁来补 |
|---|---|---|
| `import_memory()`/`archive_to_memory()` 具体改动量与优先级 | 落地 | owner（melee） |
| 教训"自动合并/滚动归档"机制 | 后续增强 | 后续会议 |
| amazon-fba 自建记忆系统格式细节（参照对象） | 参考 | 不在本仓、非本会范围 |

> kimi 中立性自证、R13 已闭合（§9.1-B）；不再列待补。

---

## 13. 验收对照（task 四问）

| task 四问 | 落点 | 状态 |
|---|---|---|
| #1 中立性自证（两证人各自亲答） | §9.1：hermes exec ✅ / kimi 评审补答 ✅ | **闭合**（独立性诚实标注：kimi 为评审补答） |
| #2 盲点/风险 | §9.2：R1–R16 | 已答 |
| #3 MVP 范围 | §9.3 | 已答 |
| #4 最小可用格式 | §11.1–11.4 | 已答（不依赖 Claude 专属语法） |
| 主人补充：教训库 + 防膨胀 | §6 / §8.2 / R16 | 已设计 |

定位/位置/结构/写入/召回五项骨架：§3 / §4 / §5+§6 / §7 / §8 全部落点。

---

## 14. 圆桌裁决与本次修订

- **圆桌第 1 轮裁决：PASS**（验证席 kimi，`minutes/iter-1-kimi-review.md`）：红线守住（仅新增设计文档、无代码改动、未建目录）；四问闭合；源码锚点 `_slug`@:120 / `import_memory`@:171 / `write_conclusion`@:199,调用@:337 均核对一致。
- **本次 v2 修订（主持人，会后）**：① 回写 kimi 自证（§0/§9.1）；② 修 §1 与召回的"替掉 vs 降级"措辞矛盾（kimi MEDIUM）；③ 修源指针路径基准（R14）、记 `_slug` CJK（R15）；④ **并入主人补充：教训库 `LESSONS.md` + 防膨胀分层召回 + 归档门槛修正**（§6 / §8.2 / §3 / R16）。
