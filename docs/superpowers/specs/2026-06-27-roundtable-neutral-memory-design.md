# 圆桌中立持久记忆（roundtable-memory）— 设计文档（spec）

- 日期：2026-06-27
- 状态：设计草案（圆桌审议产物，待验证席终审 PASS/BLOCK）
- 作者：Claude Code（拉姆，综合席/单写者）+ melee
- 圆桌会话：`20260627-122306-任务-为-loop-engine-圆桌设计一套-`
- 证人：hermes（DeepSeek，已自证）/ kimi（Moonshot，**本轮未发言 → 待补**）
- 红线：本文档**只设计、不落地**——不改圆桌任何现有代码、不真建 `roundtable-memory/` 目录。

---

## 0. 综合席诚实声明（先把缺口摆在最前）

本会要求两个异质证人（hermes、kimi）**各自亲答**第 1 条"中立性自证"，互为交叉验证。截至综合落盘时：

- ✅ **hermes（DeepSeek）已亲答**：`minutes/iter-1-hermes-exec.md` 完整覆盖 #1–#4。
- ⚠️ **kimi（Moonshot K2.7）本轮尚未产出任何 exec 发言**：本会话 `minutes/` 下只有 `iter-1-claude-plan.md`、`iter-1-hermes-exec.md`、（给综合席的）`iter-1-claude-exec.md`，**无 `iter-1-kimi-exec.md`**（已全 session grep 核实，其余 session 的 kimi 文件均属别的任务）。

因此本文档中所有"kimi 证人结论 / kimi 强编码视角的风险复核 / kimi 模板意见"**一律标「待补」**。本会铁律（task.md【红线】）：*缺口 = 重读 / 明说，绝不脑补*——前几轮综合席曾在工具结果异常时幻觉出不存在内容并空转，本会不重蹈。**交叉验证目前是「单证人 + 待补」状态，这是验证席终审时必须正视的中立性缺口。**

---

## 1. 结论（一句话）

为 loop-engine 圆桌建一个**自己的、进 git、任何 agent 都能独立读取**的持久记忆 `roundtable-memory/`：**档案馆定位**（写一次、只读归档，非活台账），落在 **repo 根**（git 版本化），用 **`INDEX.md`（项目→主题两级索引）+ `<project>/<topic>.md`（叶子定稿）** 两层结构；写入靠 conductor 散会时在 `write_conclusion()` 后加一步 **`archive_to_memory()`（纯 Python、在指挥进程内跑、不调用任何座位 agent → 天然 agent 无关）**；召回靠两条 MVP——**①进 git 谁 clone 谁被动可读；②记忆桥 `import_memory()` 改读这个 git 化的 INDEX+叶子**（替掉现读 gitignored 散落 conclusion）。格式刻意**只用标准 markdown**（标准链接、无 `[[]]`、无 frontmatter、无 `/→-` 路径映射），以保证非-Claude 座位零打折读取。

---

## 2. 背景与问题（为什么开这会）

### 2.1 现状的死结

圆桌的会议成果现存于 **gitignored** 的 `.roundtable/sessions/<id>/KB/conclusion.md`（`.gitignore` 第 2 行 `.roundtable/` 把整棵树排除）。由此两个致命后果：

1. **不进 git**：换机器 / 重新 clone 即全丢，成果没有持久落点。
2. **召回只走 Claude 体系**：记忆桥 `conductor.import_memory()`（`skills/loop-engine/bin/conductor.py:171`）汇集的三个源里，主体是 **Claude 私库** `~/.claude/projects/<repo路径 /→- 映射>/memory/*.md`，外加 gitignored 的散落 conclusion。hermes / kimi **读不到 Claude 私库**，只能靠记忆桥把内容转述进黑板。

**实锤（非推断）**：本会话 `KB/imported-memory.md` 的实际构成 = **6 份 `## Claude 项目记忆 · *.md`**（来自 Claude 私库）+ **7 份 `## 过往会话结论 · <session>`**（来自 gitignored conclusion）。两类来源**没有一个**是 git 版本化、agent 中立的。

→ 结论：圆桌实质沦为 **"Claude 的延展工具"**——其他 agent 一旦离开圆桌（不经记忆桥转述）就读不到任何圆桌成果。本会要打破这个死结。

### 2.2 本会的目标与红线

- **目标**：给圆桌一个进 git、agent 无关、任何 agent 独立可读的持久记忆。
- **红线（task.md）**：本会**只产设计文档**，不改现有代码、不真建目录、缺口标"待补"绝不编造。

---

## 3. 定位：档案馆型 MVP

| 维度 | 决策 | 理由 |
|---|---|---|
| 性质 | **档案馆**（写一次、只读归档） | 存"这次圆桌定了什么"的定稿成果，不是随时改写的活台账 |
| 复杂度 | **先 MVP 能 work，不过度工程** | 明确**砍掉** amazon-fba 那套防漂移机械守卫 / 不变式 / L1 绝对规则层 |
| 写入触发 | conductor 散会时自动归档（详见 §6） | agent 无关、零人工 |
| 召回 | 仅两条（进 git 被动可读 + 记忆桥改读，详见 §7） | recall 命令、开局 hook 自动召回属**后续非 MVP**，本会不做 |

**与主持人/主人已对齐的骨架一致**（task.md【骨架】），本会在其上审议补强，不推翻大方向。

---

## 4. 位置：repo 根 `roundtable-memory/`，进 git

```
<repo>/
├── .roundtable/              # gitignored（.gitignore 第 2 行）→ 会话过程态，会丢
│   └── sessions/<id>/KB/conclusion.md
└── roundtable-memory/        # ★新增，git 版本化 → 持久成果，不丢
    ├── README.md             # 冷启动说明（见 §9 增项）
    ├── INDEX.md              # L2 两级索引（项目→主题）
    ├── agents/               # L3 叶子：项目 = agents
    │   └── <topic>.md
    ├── amazon-fba/
    │   └── <topic>.md
    ├── finance/
    └── _meta/                # 跨项目 / 圆桌自身的议题
        └── <topic>.md
```

**为什么在 repo 根、绝不放 `.roundtable/` 下**：`.roundtable/` 被 gitignore，放进去等于继续丢。`roundtable-memory/` 放 repo 根才能进 git。

**gitignore 实证（非推断）**：当前 `.gitignore` 全文为 `.venv/` / `.roundtable/` / `__pycache__/` / `*.pyc` / `*.png` / `.playwright-mcp/`——**没有一条匹配 `roundtable-memory/`**，故该目录默认会被 git 追踪，无需额外动作。（风险 §8-R6 给出"防未来误伤"的缓解。）

---

## 5. 结构：INDEX + 叶子（三层砍 L1 的极简版）

参考 amazon-fba 三层记忆，**砍掉 L1 绝对规则层**，只留：

- **L2 索引 `roundtable-memory/INDEX.md`**：按 **项目 → 主题** 两级。每条一行：`显示名 + 日期 + 一句话状态/结论 + 指向叶子的链接`。
- **L3 叶子 `roundtable-memory/<project>/<topic>.md`**：该议题历次圆桌的定稿成果，固定分节（议题 / 结论 / 关键决策 / 源指针 / 历次更新）。

**项目划分**：`agents` / `amazon-fba` / `finance`；**跨项目或圆桌自身**的议题归 `_meta/`。`<project>` 是**项目名**，不是路径映射产物（与 Claude 私库的 `/→-` 路径映射无关 → 这条 Claude 隐含假设不传染到新设计，见 §8-中立性）。

完整模板见 §10。

---

## 6. 写入设计：`archive_to_memory()`（纯 Python · agent 无关）

### 6.1 插入点（有真实行号锚点）

`conductor.py` 的 `run()` 收尾段（`skills/loop-engine/bin/conductor.py:336-339`）现为：

```python
status = status or "CAP"
write_conclusion(repo, task, status, final_it, verdicts)   # :337
reporter.finish(status, final_it)
return {"PASS": 0, "ERR": 1, "CAP": 2}[status]
```

设计：在 `write_conclusion(...)` **之后**、`reporter.finish(...)` 之前插一行 `archive_to_memory(...)`。**本会不落地此改动**（红线）。

### 6.2 为什么"天然 agent 无关"

`archive_to_memory()` 是 `conductor.py` 里的一个**纯 Python 函数**，在**指挥进程自身**执行（与 `write_conclusion` / `import_memory` 同层），**不经 `run_seat()` 调用任何座位 agent、不依赖任何 agent 的工具链或私库**。所以"写入"这一侧从设计上就与 agent 解耦——无论本轮在座的是 claude、hermes 还是 kimi，归档行为完全一致。

### 6.3 函数职责（设计草案 — 仅描述，不落地）

```python
def archive_to_memory(repo, task, status, rounds, verdicts) -> None:
    """散会归档：把本会定稿成果落到 git 版本化的 roundtable-memory/ 叶子，并更新 INDEX。
    纯标准库、指挥进程内执行、不调用任何座位 agent。"""
    # ① 归档门槛：只归档「定稿」成果。
    #    建议 status == "PASS" 才归档（档案馆 = 定稿成果；BLOCK/CAP/ERR 非定稿，不污染档案馆）。
    #    —— 设计决策，见 §8-R11，待 kimi 复核。
    # ② 定项目 project：默认取圆桌所在 repo 对应项目名；跨项目→ _meta/（需主持人显式指定）。
    # ③ 定 topic slug：复用 conductor 既有 _slug()（conductor.py:120）规则，保证与会话命名同源。
    # ④ 叶子路径 leaf = roundtable-memory/<project>/<topic>.md
    #    - 不存在 → 按 §10 模板新建（议题/结论/关键决策/源指针/历次更新）。
    #    - 已存在 → 刷新「结论 / 关键决策」为最新定稿，并在「历次更新」表 append 一行
    #      （append-only 历史，不删旧轨迹）。合并策略见 §8-R2/R12，待 kimi 复核。
    # ⑤ 先写叶子，成功后再更新 INDEX.md 对应行（顺序见 §8-R5 回滚论证）。
    # ⑥ 全程 try/except 包裹、失败不抛（与 write_conclusion 同样的 OSError 容错风格）。
```

### 6.4 与 `write_conclusion` 的职责分界（去重，采纳 hermes 风险 #7）

| | `write_conclusion()` → `.roundtable/.../conclusion.md`（gitignored） | `archive_to_memory()` → `roundtable-memory/<project>/<topic>.md`（git） |
|---|---|---|
| 内容 | **单次会话完整记录**：任务原文、各轮裁决、diffstat、checkpoint 提交、minutes 清单 | **定稿成果摘要**：这次会定了什么（结论 + 关键决策 + 源指针） |
| 性质 | 审计轨迹（过程态，可丢） | 知识积累（成果态，进 git 持久） |
| 关系 | 不删、保留 | 新增；其"源指针"反向指回 conclusion / minutes 做溯源 |

两者内容会重叠但职责不同，**不冲突**。

---

## 7. 召回设计（MVP 只做两件）

### 7.1 ① 进 git → 谁 clone 谁被动可读（零机制依赖）

任何 agent clone 仓库后，直接 `read roundtable-memory/INDEX.md` → 顺标准 markdown 链接读叶子。**不需要记忆桥、不需要 Claude 私库、不需要任何 agent 专属解析**。这一条就让 hermes / kimi 脱离圆桌也拿得到成果——是打破 §2 死结的根本一招。

### 7.2 ② 记忆桥 `import_memory()` 改读 git 化的 INDEX + 叶子

现状（`conductor.py:171-196`）`import_memory()` 三源：
1. 仓库 `CLAUDE.md`（:177-178）
2. Claude 私库 `~/.claude/projects/<mapped>/memory/*.md`（:179-182，经 `/→-` 映射，**非 Claude 读不到**）
3. 遍历 gitignored `sessions/*/KB/conclusion.md`（:184-191，散落、会丢）

**设计改造（仅描述，不落地）**：

- **新增/置顶主源**：若 `roundtable-memory/INDEX.md` 存在，将其内容 + 各叶子标题摘要附进 `imported-memory.md`（作为新增节 `## 圆桌持久记忆（roundtable-memory/）`）。因其**进 git、agent 中立**，列为**主源**。
- **降级源 3**：现读 gitignored 散落 conclusion 从"主要召回路径"**降级为审计补充**（或保留兜底，避免归档未覆盖的历史断档）。
- **源 2（Claude 私库）降为补充源**：仅加载 `roundtable-memory/` 未覆盖的条目（去重，采纳 hermes 风险 #4）。
- **去重原则**：以 `roundtable-memory/` 为主源；同一知识若两源都有，主源优先，并在 `imported-memory.md` 标注每节来源，避免混淆。

> 〔**后续非 MVP，本会不做**：独立 `recall` 命令、各 agent 开局 hook 自动召回。〕

---

## 8. 中立性自证 + 风险缓解

### 8.1 第 1 条 · 中立性自证（最关键）

#### 证人 A：hermes（DeepSeek）— 已亲答 ✅

> 来源：`minutes/iter-1-hermes-exec.md`，hermes 自述已实读 KB 全 7 文件、`conductor.py` 全 361 行、两份 conclusion 样本、现有 spec、`.gitignore`。

**结论：能读到、能读懂、能用上。唯一打折点是 `[[]]` 指针，有替代写法。** 逐项：

| 元素 | 对 hermes（`read_file` / ripgrep，无 wiki-link/无 frontmatter schema/无 `/→-` 概念）的影响 | 处理 |
|---|---|---|
| 纯 markdown（INDEX + 叶子） | ✅ 无障碍，`read_file` 直接读全文 | 采用 |
| 两级 INDEX（项目→主题） | ✅ 能人读、能 ripgrep、能按明确路径找叶子 | 采用 |
| `[[project/topic]]` wiki-link | ⚠️ **打折**：Claude 内置自动解析，hermes 只当纯文本，需额外约定才会解析 | **弃用**，改标准 markdown 链接 |
| YAML frontmatter | 读得见但不理解其为"元数据"；档案馆定位不需要 | **弃用**，元数据改放标题下 kv 列表 |
| `/→-` 路径映射 | 不适用：`<project>` 是项目名非路径映射产物 | **不传染**，无需处理 |

**采纳的 agent 友好硬规则（写进格式约定）**：

1. **链接一律用标准 markdown**：`[显示名](agents/topic.md)`、叶子间 `[文本](../agents/other.md)`——Claude / hermes / 人类 / 任意 markdown 渲染器都能跟，零专属解析。**全程禁用 `[[]]`**。
2. **不用 frontmatter**：元数据（日期 / 项目 / 会话 / 状态）放叶子标题下的 key-value 列表，纯 markdown。
3. **不依赖 `/→-` 映射**：`<project>` 用项目名。
4. **源指针用相对路径**：指向 `.roundtable/sessions/` 原始 conclusion / minutes（即便 gitignored，本地磁盘仍可查）。

#### 证人 B：kimi（Moonshot K2.7）— **待补** ⚠️

> **kimi 本轮未产出 exec 发言**（§0 已核实）。其"以自己真实读取方式做独立中立性自证、挑出对 Moonshot 不友好的 Claude 专属语法"这一最关键的交叉验证**尚未发生**。
>
> **待补项**：
> - kimi 自己能否零打折读 `roundtable-memory/`（纯 markdown + 标准链接）？
> - Moonshot 侧有无 hermes 未覆盖的专属假设打折点？
> - 标准 markdown 链接 `[text](path.md)` 对 kimi 是否友好？（hermes 在其发言里明确说"这是 kimi 自己需在 #1 回答的，雷姆不代答"。）
>
> **综合席不代答、不编造**。交叉验证当前 = **单证人（hermes）+ kimi 待补**。验证席终审需把此列为中立性未闭合项。

### 8.2 第 2 条 · 风险缓解表

下表 R1–R10 整合自 **hermes**（已亲答）；R11–R12 为**综合席**从源码读出的设计决策风险。标 **[待 kimi 复核]** 的需第二证人强编码视角终审；标 **[待 kimi 补]** 的本由 kimi 强编码视角主答，**本轮缺**。

| # | 风险 | 严重度 | 缓解 | 来源 |
|---|---|---|---|---|
| R1 | **并发写 INDEX 冲突**：两会话同时 archive，后写覆盖先写 | 低（MVP 单用户串行，conductor 单进程） | MVP 依赖串行前提；后续如需并发加 `fcntl.flock` 或写临时文件 + 原子 `rename` | hermes |
| R2 | **叶子命名碰撞**：同项目下两议题 slug 相同，后者覆盖前者 | 中 | 写入前查文件是否存在；存在且内容不同则追加 `-2` 后缀或拒写报错；INDEX 中 topic 名含 slug，冲突可见 | hermes [待 kimi 复核] |
| R3 | **跨项目归类歧义**：一会同涉 agents + amazon-fba，归哪个？ | 中 | 默认归圆桌所在 repo 对应项目；`_meta/` 仅用于显式跨项目（主持人归档时指定）；叶子内 `项目` 字段注明归属 | hermes [待 kimi 复核] |
| R4 | **与记忆桥/conclusion 衔接去重**：同知识被读两次（Claude 私库 + roundtable-memory 叶子） | 中 | `import_memory()` 以 `roundtable-memory/` 为主源，Claude 私库降补充源（仅加载主源没有的）；`imported-memory.md` 标注每节来源 | hermes（见 §7.2） |
| R5 | **archive 失败回滚**：写叶子成功、更新 INDEX 失败 → 孤儿；或反之 → 死链 | 中 | **先写叶子、后更新 INDEX**。叶子失败则整体放弃、不动 INDEX；INDEX 失败则叶子无害（暂不被发现，后续可扫描重建）。不搞两阶段提交（过度工程） | hermes |
| R6 | **gitignore 误伤**：将来有人加 `roundtable*` 到 .gitignore 会误伤 | 低 | 在 `.gitignore` 加注释 `# roundtable-memory/ 是 git 版本化持久记忆，勿 ignore`；或放 `.gitkeep` 确保目录被追踪 | hermes |
| R7 | **conclusion ↔ archive 语义重叠**：什么写哪个？ | 低 | 见 §6.4 职责分界：conclusion = 会话完整审计轨迹；叶子 = 定稿成果摘要 | hermes |
| R8 | **INDEX 损坏无法自动重建** | 低 | MVP 依赖 git 回滚；后续可加 `rebuild-index.sh` 扫描叶子重建 | hermes |
| R9 | **conductor 崩溃致归档中断**：conclusion 写了、archive 没写 | 低 | conclusion 仍在本地磁盘，下轮 `import_memory()` 仍读得到；后续可加"扫描未归档 conclusion"恢复工具 | hermes |
| R10 | **人改叶子 vs 下次归档覆盖** | 低 | MVP 约束 archive 只写不读已有内容；人工修改应作为下一轮圆桌输入，而非直接改叶子 | hermes [待 kimi 复核] |
| R11 | **归档门槛未定**：是否每次散会都归档？BLOCK/CAP/ERR 也归档会污染档案馆 | 中 | **设计决策**：建议**仅 `status=="PASS"` 归档**（档案馆 = 定稿成果）。非定稿不进档案馆 | 综合席 [待 kimi 复核] |
| R12 | **同 topic 重复归档的合并策略未定**：覆盖 vs 追加 | 中 | **设计决策（MVP 推荐）**：刷新「结论/关键决策」为最新 + 「历次更新」表 append 一行（保留轨迹、不搞版本树）。见 §6.3-④ | 综合席 [待 kimi 复核] |
| R13 | **Moonshot 侧专属打折点** | ? | **本由 kimi 强编码视角主答** | **[待 kimi 补]** |

### 8.3 第 3 条 · MVP 范围（增删）

> hermes 评估，综合席采纳。kimi 的"有无过度工程/遗漏"独立评估 **[待补]**。

- **该砍的**：hermes 评"**无**"——当前 MVP（INDEX + 叶子 + `archive_to_memory()`）已是极简，再砍无物。综合席同意；并重申 task 已明确**砍掉** fba 防漂移机械守卫 / 不变式 / L1 绝对规则层。
- **该加的（MVP 必需但易漏）**：
  1. **`roundtable-memory/README.md`**：冷启动说明（agent clone 后知道这目录是什么、怎么读）。模板见 §10.3。
  2. **`import_memory()` 改读**：若建了目录但记忆桥不读，等于白建（§7.2 已设计）。
  3. **`.gitignore` 防误伤注释**（R6）。

---

## 9. 实施清单（供后续落地参考 — 本会不执行）

> 红线：本会**只产文档**。以下为将来真正落地时的最小动作清单，**本轮一律不做**。

1. 真建 `roundtable-memory/`：`INDEX.md` + `README.md` + 各项目空目录（`.gitkeep`）。
2. `conductor.py` 加 `archive_to_memory()`，在 `:337 write_conclusion` 后调用一行。
3. `conductor.py` 改 `import_memory()`：新增 roundtable-memory 主源、私库降补充、conclusion 降审计补充。
4. `.gitignore` 加防误伤注释。
5. （后续非 MVP）`rebuild-index.sh`、未归档 conclusion 恢复工具、recall 命令、开局 hook。

**待补**：第 2/3 步的具体代码改动量与优先级需 owner 确认（hermes 亦标此为待 owner 项）。

---

## 10. 最小可用格式（模板）

> 设计要求：**人类可读 + 各 agent 可解析 + 不依赖 Claude 专属语法**。以下模板采纳 hermes 的雏形（去 frontmatter、标准链接），kimi 的模板意见 **[待补]**。

### 10.1 `INDEX.md` 模板

```markdown
# 圆桌记忆索引（INDEX）

> 两级结构：项目 → 主题。每行一条：显示名 + 日期 · 一句话状态/结论 → 指向叶子。
> 链接约定：全部为相对本目录的**标准 markdown 链接**（禁用 [[]]）。
> 更新规则：每次圆桌散会由 conductor 的 archive_to_memory() 自动追加/更新；人类亦可手工编辑。

## agents

- [hermes 与 Claude 共存](agents/hermes-agent-coexists.md) — 2026-06-27 · 两 AI agent 同机安装位置/配置/能力边界/共存约定
- [loop-engine 圆桌架构](agents/loop-engine-roundtable.md) — 2026-06-24 · 黑板架构圆桌设计/组件/座位脚本/运行方式（已实现并验证）
- [Kimi 迁移方案](agents/kimi-migration-plan.md) — 2026-06-27 · 三项目→Kimi 承接方案（PLAN v5，圆桌4轮 PASS，仅方案未执行）

## amazon-fba

- （尚无归档）

## finance

- （尚无归档）

## _meta

- [圆桌中立记忆设计](_meta/roundtable-neutral-memory-design.md) — 2026-06-27 · roundtable-memory 系统的设计决策与格式约定
```

**字段说明**：

- 每条一行，格式：`- [显示名](相对路径) — YYYY-MM-DD · 一句话状态/结论`
- 相对路径指向 `roundtable-memory/<project>/<topic>.md`
- 日期取圆桌会话日期，ISO 格式
- 空项目节保留并标"（尚无归档）"，让索引结构稳定、可预期

### 10.2 叶子 `<topic>.md` 模板（分节：议题/结论/关键决策/源指针/历次更新）

```markdown
# 议题标题（人类可读的一句话）

- **日期**：2026-06-27
- **项目**：agents
- **圆桌会话**：20260627-122306-任务-为-loop-engine-圆桌设计一套-
- **状态**：定稿 / 草稿 / 已推翻
- **关联议题**：[Kimi 迁移方案](../agents/kimi-migration-plan.md)

## 议题

（本议题要解决什么、为什么开圆桌——1-3 段，人类能看懂）

## 结论

（圆桌达成的最终结论——最重要，agent 召回时优先读这里）

## 关键决策

- 决策 1：……（理由：……）
- 决策 2：……（理由：……）

## 源指针

- KB 结论：`.roundtable/sessions/<id>/KB/conclusion.md`
- 座位发言：`.roundtable/sessions/<id>/minutes/`
- 产出文件：`docs/.../<deliverable>.md`

## 历次更新

| 日期 | 圆桌会话 | 变更摘要 |
|------|---------|---------|
| 2026-06-27 | 20260627-122306 | 初始定稿 |
```

**设计要点**：

- **无 frontmatter**：元数据全在标题下 kv 列表，纯 markdown，任意 agent 可读。
- **无 `[[]]`**：关联议题用标准相对链接 `[文本](../project/topic.md)`。
- **源指针用相对路径**：指向 `.roundtable/sessions/` 原始结论与 minutes（gitignored 但本地可查）。
- **历次更新表 append-only**：不删历史，每次圆桌追加一行（呼应 §6.3-④ / R12）。
- **分节固定**：`议题 / 结论 / 关键决策 / 源指针 / 历次更新`——人类扫读有结构，agent 按 `## ` 标题切分即可解析。

### 10.3 `README.md` 模板（冷启动说明 — hermes 增项 §8.3）

```markdown
# 圆桌持久记忆（档案馆）

此目录是 loop-engine 圆桌的 **git 版本化持久记忆**。每次圆桌会议的定稿成果归档于此。

- `INDEX.md` — 两级索引（项目→主题），每行指向一个叶子文件
- `<project>/<topic>.md` — 叶子文件，该议题的定稿成果

任何 agent 都可通过读取本目录独立获取圆桌历史成果，无需依赖特定 agent 的私用记忆系统。
链接一律为标准 markdown（无 [[]]、无 frontmatter）。
```

---

## 11. 待补清单（汇总 — 缺口集中可查）

| 项 | 性质 | 谁来补 |
|---|---|---|
| kimi 中立性自证（第二证人，#1 交叉验证） | **会议关键缺口** | kimi exec（本轮未发言） |
| Moonshot 侧专属打折点（R13） | 风险 | kimi 强编码视角 |
| kimi 对 MVP 过度工程/遗漏的独立评估（#3） | 范围 | kimi exec |
| kimi 的 INDEX/叶子模板意见（#4） | 格式 | kimi exec |
| R2/R3/R10/R11/R12 的强编码视角复核 | 风险终审 | kimi |
| `import_memory()`/`archive_to_memory()` 具体改动量与优先级 | 落地 | owner（melee） |
| amazon-fba 自建记忆系统格式（参照对象细节） | 参考 | 不在本仓、非本会范围 |

---

## 12. 验收对照（task 四问是否正面回答）

| task 四问 | 本文档落点 | 状态 |
|---|---|---|
| #1 中立性自证（两证人各自亲答） | §8.1：hermes ✅ 已答；kimi ⚠️ 待补 | **半闭合**（诚实标注） |
| #2 盲点/风险（逐条风险+缓解） | §8.2：R1–R13 表 | 已答（含待 kimi 复核项） |
| #3 MVP 范围（增删） | §8.3：砍=无 / 加=README+import_memory+gitignore注释 | 已答（kimi 独立评估待补） |
| #4 最小可用格式（INDEX + 叶子模板） | §10.1/10.2/10.3 | 已答（不依赖 Claude 专属语法） |

定位/位置/结构/写入/召回五项骨架：§3 / §4 / §5 / §6 / §7 全部落点。

---

## 13. 综合席自检记录（声称 vs 正文一致）

落盘后由综合席本人 grep 核对（命令与结果见会议 transcript）。核对项：

1. 全文是否出现 `[[` wiki-link → 应**仅在"禁用/弃用"语境**出现，不作为实际链接语法。
2. 凡声称"两证人""kimi 已答"处 → 必须同时标注 kimi **待补**，无裸称两证人都完成。
3. 所有"待补"是否集中可查（§11）且与正文标注一致。
4. 行号锚点（`conductor.py:337` / `:171` / `:120` 等）与正文引用一致。

**自检结论（综合席实跑 grep，2026-06-27）：PASS — 无不一致。**

- 项1：`[[` 全文 8 处，**均**在"无/弃用/禁用/打折说明"语境，无一处作实际链接语法。✅
- 项2：「两证人/交叉验证」全文 7 处，**均**同时标注 kimi 未发言/待补/半闭合，无裸称"两证人都完成"。✅
- 项3：所有 kimi 结论性内容均带 `[待补]/[待 kimi 复核]/[待 kimi 补]`；正文仅两处 `Kimi 迁移方案` 为模板内真实历史叶子示例（非冒充证人发言）。✅
- 项4：行号锚点 `_slug`@:120、`import_memory`@:171、`write_conclusion`@:199/调用@:337、`run()` 收尾@:336-339 均与 `conductor.py` 源码逐一核对一致。✅
