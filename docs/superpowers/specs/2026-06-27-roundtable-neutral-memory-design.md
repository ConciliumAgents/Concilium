# 圆桌中立持久记忆（roundtable-memory）— 设计文档（spec）

- 日期：2026-06-27
- 状态：设计草案 **v3**（v2 经圆桌评审揪出 2 个 HIGH，本版并入解法闭合 → **ready-to-implement**，待执行会落地）
- 作者：Claude Code（拉姆，综合席/单写者）+ melee
- 圆桌会话：设计 `20260627-122306`（v1 PASS）/ 评审 `20260627-130354`（v2 三轮 BLOCK，揪出 2 HIGH）
- 证人：hermes（DeepSeek，exec 自证）/ kimi（Moonshot，exec + 评审两轮）→ 两证人均确认中立（§9.1）
- 红线：本文档**只设计、不落地**——不改圆桌任何现有代码、不真建 `roundtable-memory/` 目录。

---

## 0. 综合席诚实声明（缺口与闭合史）

- ✅ **hermes（DeepSeek）** exec 亲答 #1–#4（设计会 `iter-1-hermes-exec.md`）。
- ✅ **kimi（Moonshot）** 设计会 exec 缺席（plan 未派活）、评审会 exec 亲答（85KB，`130354/iter-1-kimi-exec.md`）+ 两轮验证席裁决。其中证人自证已回写 §9.1-B，**诚实标注独立性**：设计会为评审席补答、评审会为独立 exec。
- ⚠️→✅ **v2 两个 HIGH（评审会 kimi 终审 BLOCK）已在本 v3 闭合**：详见 §6.4 / §7 / §8 / §10。

> 铁律：缺口 = 重读 / 明说，绝不脑补。评审会 CAP 暴露的"任务设计死锁"（只评审禁改 spec ↔ 判 spec 是否 ready）与"引擎卡死探测未生效"两条，已列为 `LESSONS.md` 首批教训候选（§6.2）。

---

## 1. 结论（一句话）

为 loop-engine 圆桌建一个**自己的、进 git、任何 agent 都能独立读取**的持久记忆 `roundtable-memory/`：**档案馆定位**（写一次、只读归档），落 **repo 根**（git 版本化）。含两类知识、各有其家：**成果库** `<project>/<topic>.md`（PASS 定稿，`INDEX.md` 索引）+ **教训库** `LESSONS.md`（失败/协作教训，通用核心 + 分项目，让协作越跑越稳）。写入靠 conductor 散会 `archive_to_memory()`，召回靠 `import_memory()` 改造（**均加特性开关、默认关、Phase 0-4 零回归落地**）。格式只用标准 markdown（无 `[[]]`、无 frontmatter、无 `/→-`），非-Claude 座位零打折（两证人已确认）。

---

## 2. 背景与问题

### 2.1 现状的死结

圆桌成果存于 **gitignored** 的 `.roundtable/sessions/<id>/KB/conclusion.md`（`.gitignore:2`）。后果：① 不进 git，换机器/clone 即丢；② 召回只走 Claude 体系——`import_memory()`（`conductor.py:171`）汇集的源里主体是 Claude 私库 `~/.claude/projects/<repo /→- 映射>/memory/*.md` + gitignored conclusion，hermes/kimi 读不到私库。**实锤**：本会 `imported-memory.md` = 6 份 Claude 私库 + 7 份 gitignored conclusion，**无一是 git 化、agent 中立的**。→ 圆桌沦为 "Claude 延展工具"。

### 2.2 目标与红线

- **目标**：给圆桌一个进 git、agent 无关、任何 agent 独立可读的持久记忆，**能积累教训、自我改进、又不随时间膨胀**。
- **红线**：本会只产设计文档，不改代码、不真建目录、缺口标"待补"绝不编造。

---

## 3. 定位：档案馆型 MVP + 改动边界

| 维度 | 决策 | 理由 |
|---|---|---|
| 性质 | **档案馆**（写一次、只读归档） | 存定稿成果 + 提炼后教训，非活台账 |
| 复杂度 | **MVP，不过度工程** | 砍掉 amazon-fba 的防漂移机械守卫/不变式/L1 |
| 归档门槛 | **PASS → 成果库**；**任何会的 `## 教训` 节 → 教训库** | 成果只收定稿；失败教训尤其值钱 |
| 召回 | 成果按需 + **教训分层防膨胀**（§6.3 / §8） | recall 命令、开局 hook 属后续非 MVP |
| **改动边界**（主人确认） | **数据目录 `roundtable-memory/` 全新独立**（不碰任何老文件）；**引擎钩子改 `conductor.py`**（archive + import），但**特性开关默认关 + Phase 0-4 零回归护栏**（§10） | 召回飞轮绑定 conductor 的 `import_memory()`，无法完全独立；护栏保证现有圆桌随时退回原样、零回归 |

> 与"Kimi 迁移方案 PLAN.md"区分：那个是"不动 claude 现有文件、产物全隔离"的迁移备份；**本 roundtable-memory 是给圆桌引擎本身加器官**，数据独立但引擎钩子必须改 conductor（带护栏）。

---

## 4. 位置：repo 根 `roundtable-memory/`，进 git

```
<repo>/
├── .roundtable/                 # gitignored → 过程态，会丢
└── roundtable-memory/           # ★新增，git 版本化 → 持久
    ├── README.md                # 冷启动说明（§11.4）
    ├── INDEX.md                 # 成果索引：项目→主题两级
    ├── LESSONS.md               # ★教训库：通用铁律 + 分项目（§6）
    ├── agents/<topic>.md        # 成果叶子
    ├── amazon-fba/<topic>.md
    ├── finance/<topic>.md
    └── _meta/<topic>.md         # 跨项目 / 圆桌自身
    # （后续）LESSONS-archive/    老教训滚动归档，不参与召回
```

**gitignore 实证**：`.gitignore` 6 行无一匹配 `roundtable-memory/`，默认被追踪。防未来误伤见 §9.2-R6。

---

## 5. 成果库结构：INDEX + 叶子

- **L2 索引 `INDEX.md`**：项目 → 主题两级。每条一行 `[显示名](相对路径) — YYYY-MM-DD · 一句话结论`。
- **L3 叶子 `<project>/<topic>.md`**：定稿成果，分节 议题/结论/关键决策/源指针/历次更新。

`<project>` = 项目名（非 `/→-` 映射产物）；跨项目归 `_meta/`。模板见 §11。

---

## 6. 教训库 `LESSONS.md`（让协作越跑越稳）

### 6.1 为什么要它

失败教训是另一种成果。成果库只收 PASS 定稿会丢掉它们；`LESSONS.md` 收容并在**召回时主动喂给座位**，形成"每次的坑下次自动带上"的飞轮。（先例：amazon-fba CLAUDE.md 专设"幻觉事件复盘机制"。）

### 6.2 结构：两区

```markdown
# 圆桌教训库（LESSONS）

## 通用铁律（每次开会全量置顶召回 · 刻意保持小而收敛）
- 工具结果异常/有缺口时重读或明说，绝不脑补。（源：注入幻觉空转）
- 综合席"已修"摘要每条正文必须真有，改完自 grep。（源：摘要↔正文断层）
- 总指挥派活必须覆盖每个"该自证/发言"的座位。（源：设计会 kimi exec 缺席）
- review-only 会的裁决标准应是"评审是否充分/blocker 是否查清"，不可是"文件是否完美 ready"——否则禁改+判ready 结构性死锁、空转 CAP。（源：评审会 CAP）
- participants 以实际在座为准，勿据硬编码默认派活给已下桌座位。（源：座位漂移 bug）

## 分项目教训（开会只召回当前项目这一节）
### agents
- （示例）……
### amazon-fba
### finance
```

### 6.3 防膨胀三招

| 招 | 治什么 | 做法 | MVP？ |
|---|---|---|---|
| ① 存精炼不存原始 | 单条体积 | 每条一行：教训+怎么避+源指针；原始留 conclusion | ✅ |
| ② 分层召回 | "读"膨胀 | 召回 = `通用铁律`全量 + **仅当前项目节**；不读他项目、不读原始纪要（§8.2） | ✅ |
| ③ 教训"毕业" | "写"膨胀（根治） | 同类→合并进通用铁律；过时标 `SUPERSEDED`；量大→`LESSONS-archive/` | ⚠️ 去重/SUPERSEDED 靠写入纪律（MVP）；自动合并/归档（后续） |

**诚实边界**（kimi 评审 MEDIUM 确认）：单项目节仍随会议次数线性增长；通用铁律"小而收敛"靠**写入纪律**非自动魔法。MVP 可接受，但 README 须显性化写入纪律 + 约定前 10 轮后复查通用铁律条数。

### 6.4 教训的来源契约（闭合 v2-HIGH①）

v2 漏洞：spec 让 archive 抽纪要 `## 教训` 节，但**历史所有纪要根本无此节**（kimi 实测），且"通用 vs 项目"分类信号、去重均未定义 → 写读契约不完整。**v3 闭合**：

1. **写入端（需改座位 brief / 协议）**：要求 exec 座位在纪要**末尾附 `## 教训` 节**，节内用子标题 `### 通用` / `### <项目名>` 归类，每条一行。无教训则写"（无）"。
2. **MVP 抽取范围**：`archive_to_memory()` **只抽 claude 综合席纪要**（`minutes/iter-*-claude-exec.md`）的 `## 教训` 节——综合席握全上下文、重复风险最低。（后续可扩到各 exec 席。）
3. **归位规则**：`### 通用` 子节 → `LESSONS.md` 的 `## 通用铁律`；`### <项目名>` 子节 → `## 分项目教训` 对应 `### <项目名>`（不存在则建）。
4. **去重**：同一会话内按条目文本 SHA-256 去重；append 前再与目标区现有条目文本比对，重复则跳过。

---

## 7. 写入设计：`archive_to_memory()`（纯 Python · agent 无关 · 带开关）

### 7.1 插入点

`conductor.py:336-339` 收尾，在 `write_conclusion(...)` 后、`reporter.finish(...)` 前插一行 `archive_to_memory(...)`。本会不落地。

### 7.2 agent 无关 + 项目标识

纯 Python、指挥进程内执行、不调任何座位 agent。**project identifier 来源**（闭合 v2-HIGH② 的一半）：MVP 取 `Path(repo).name`（repo 目录 basename，如 `agents` / `amazon-fba-workflow` / `finance`）；跨项目归档由主持人经环境变量 `LOOP_ARCHIVE_PROJECT=_meta`（或具体项目名）显式指定。需规范短名（`amazon-fba-workflow`→`amazon-fba`）时用一个可选小映射 dict，MVP 可先直接用 basename。

### 7.3 职责（设计草案）

```python
def archive_to_memory(repo, task, status, rounds, verdicts) -> None:
    """散会归档：成果落叶子、教训落 LESSONS.md。纯标准库、指挥进程内、不调座位。
    受 LOOP_ARCHIVE 开关控制（默认 "1" 开；设 "0" 关）。全程 try/except 失败不抛。"""
    if os.environ.get("LOOP_ARCHIVE", "1") != "1": return
    try:
        project = os.environ.get("LOOP_ARCHIVE_PROJECT") or Path(repo).name
        # 【成果】仅 status == "PASS"：
        #   topic = _slug(task)（conductor.py:120；⚠ 保留 CJK，落地提供 ASCII fallback，§9.2-R15）
        #   leaf = roundtable-memory/<project>/<topic>.md：无则按 §11.2 建；有则刷新结论/决策 + 历次更新 append
        #   先写叶子、成功后更新 INDEX.md（§9.2-R5）
        # 【教训】不分成败（§6.4 契约）：
        #   读 minutes/iter-*-claude-exec.md 的 `## 教训` 节 → 按 `### 通用`/`### <项目>` 归位
        #   → append 到 LESSONS.md 对应区；同会话 + 目标区 SHA-256 去重
    except OSError:
        pass
```

### 7.4 与 `write_conclusion` 分界

conclusion = 单次会话完整审计轨迹（过程态、gitignored、可丢）；archive = 定稿成果摘要 + 提炼教训（成果态、进 git）。叶子"源指针"反指 conclusion/minutes 溯源。

---

## 8. 召回设计：`import_memory()` 改造（带开关 · 分层防膨胀 · 零回归）

### 8.1 路径一：进 git → 谁 clone 谁被动可读

任何 agent clone 后直接读 `INDEX.md` / `LESSONS.md` → 顺标准 markdown 链接读叶子，零机制依赖。打破 §2 死结的根本一招。

### 8.2 路径二：`import_memory()` 改造（闭合 v2-HIGH② 的另一半）

现状 `import_memory()`（`conductor.py:171-196`）三源（CLAUDE.md / Claude 私库 / gitignored conclusion）的读取**均无 try/except，仅 `.exists()`/`.is_dir()` 守卫**（kimi 实证 :178/:182/:191）。改造原则——**加新源不能扩大现有失败面**：

1. **特性开关默认关**：新源读取由 `LOOP_USE_ROUNDTABLE_MEMORY`（默认 `"0"`）控制；关时行为与现状**逐字一致**（零回归基线）。
2. **新源独立函数 + 整段 try/except**：新增 `_roundtable_memory(repo, project)` 读 `roundtable-memory/`，**整体 try/except 包裹**，任何异常只跳过新源、不影响旧源。
3. **教训分层召回（防膨胀）**：读 `LESSONS.md` 的 `## 通用铁律` **全量**；`## 分项目教训` 仅读 **当前 project（同 §7.2 来源）** 那一 `### <project>` 节；**不读**他项目、**不读**原始纪要。成果库 `INDEX.md` + 叶子标题作主源附入。
4. **旧三源顺手加固**：给现有 :178/:182/:191 各包 try/except（独立小改、降低既有脆弱面）。
5. **来源标注去重**：`imported-memory.md` 标每节来源；以 roundtable-memory 为主源，Claude 私库/conclusion 降补充（仅加载主源未覆盖的，**非整体替换**）。

> 〔后续非 MVP：recall 命令、各 agent 开局 hook、`LESSONS-archive/` 滚动。〕

---

## 9. 中立性自证 + 风险缓解

### 9.1 第 1 条 · 中立性自证（两证人均确认）

- **证人 A hermes（DeepSeek）**：实读 KB 7 文件 + `conductor.py` 361 行 + 两份 conclusion + `.gitignore`，结论"能读到、读懂、用上；唯一打折点 `[[]]` 有替代写法"。工具链 `read_file`/ripgrep，无 wiki-link/frontmatter/`/→-`。
- **证人 B kimi（Moonshot）**：评审会 exec 亲核 + 终审，结论"v2 格式（纯 markdown + 标准链接 + LESSONS 两区 + 无 `[[]]`/无 frontmatter/项目名）对我零打折，§9.1-B 转述无走样，R13 Moonshot 打折点=无"。
- **共识格式铁律**：① 链接一律标准 markdown，禁 `[[]]`；② 不用 frontmatter，元数据放标题下 kv 列表；③ 不依赖 `/→-`，用项目名；④ 源指针**以仓库根为基准**书写（模板顶部声明）。

### 9.2 第 2 条 · 风险缓解表

| # | 风险 | 严重度 | 缓解 | 状态 |
|---|---|---|---|---|
| R1 | 并发写 INDEX/LESSONS 冲突 | 低 | MVP 单进程串行；后续 flock/原子 rename | — |
| R2 | archive 教训抽取契约缺失 | ~~HIGH~~→闭合 | §6.4 契约（写入端附 `## 教训` 节 + 子标题分类 + 只抽综合席 + hash 去重） | ✅ v3 闭合 |
| R3 | 跨项目归类歧义 | 中 | 默认 `Path(repo).name`；`_meta/` 经 `LOOP_ARCHIVE_PROJECT` 显式指定 | 缓解 |
| R4 | 与私库/conclusion 去重 | 中 | 本库主源，旧源降补充（§8.2-5） | 缓解 |
| R5 | import 改召回主路径回归 | ~~HIGH~~→闭合 | §8.2 特性开关默认关 + 独立函数整段 try/except + 旧源加固 + §10 Phase 0-4 + smoke test | ✅ v3 闭合 |
| R6 | gitignore 未来误伤 | 低 | `.gitignore` 加注释 / `.gitkeep` | 缓解 |
| R7 | conclusion↔archive 语义重叠 | 低 | §7.4 分界 | 缓解 |
| R8 | INDEX 损坏无法自动重建 | 低 | git 回滚；后续 `rebuild-index.sh` | — |
| R9 | conductor 崩溃致归档中断 | 低 | conclusion 仍在磁盘，下轮 import 仍读到 | — |
| R10 | 人改叶子 vs 归档覆盖 | 低 | archive 只写不读已有；人改作下一轮输入 | — |
| R11 | 归档门槛 | 中 | 成果仅 PASS；教训不分成败（§3）；BLOCK/CAP 轨迹仍在 conclusion | 缓解 |
| R12 | 同 topic 重复归档合并 | 中 | 刷新结论/决策 + 历次更新 append | 缓解 |
| R13 | Moonshot 专属打折点 | — | kimi 确认：无 | ✅闭合 |
| R14 | 源指针路径基准歧义 | 低 | 模板声明"以仓库根为基准" | ✅ v2 修 |
| R15 | `_slug` CJK 文件名 | 低 | 落地 ASCII fallback / README 注明 | 缓解 |
| R16 | 教训库膨胀全量召回失控 | 中 | §6.3 三招 | 缓解 |
| R17 | 项目名 basename 与规范短名不一致 | 低 | MVP 用 basename；需要时加可选映射 dict（§7.2） | 缓解 |

### 9.3 第 3 条 · MVP 范围

- **该砍**：无（已极简；砍了 fba 守卫/不变式/L1）。
- **该加**：① README；② `import_memory()` 改读；③ `.gitignore` 注释；④ 教训库 `LESSONS.md` + 分层召回；⑤ **座位 brief 加 `## 教训` 节要求**（§6.4 写入端）；⑥ **特性开关 + Phase 0-4 + smoke test**（§10）。

---

## 10. 落地执行计划（Phase 0-4 · 零回归护栏 · 闭合 v2-HIGH②）

> 本计划即执行会的剧本。核心护栏：**新行为默认关，开关关时逐字等于 baseline**。

**Phase 0 — 基线（不改代码）**
- 干净工作树；跑一次（dry-run 或最小真跑）存 `imported-memory.md` 作 baseline；复跑确认可复现。

**Phase 1 — 数据骨架（零召回风险）**
- 建 `roundtable-memory/`：`README.md` + `INDEX.md` + `LESSONS.md`（含首批通用铁律，§6.2）+ 各项目空目录（`.gitkeep`）。
- `.gitignore` 加防误伤注释。git commit。
- 验证：`import_memory()` 输出与 baseline 一致（此阶段未改代码）。

**Phase 2 — 写入路径 `archive_to_memory()`（低风险）**
- conductor.py 加函数，在 `:337` 后调用；`LOOP_ARCHIVE` 默认开、可关；整体 try/except。
- 座位 brief 加"末尾附 `## 教训` 节（`### 通用`/`### <项目>`）"。
- 验证：真跑一次，检查 `roundtable-memory/` 叶子 + LESSONS 生成正确；`LOOP_ARCHIVE=0` 时不写。

**Phase 3 — 读取路径 `import_memory()`（高风险 · 带开关）**
- 新增 `_roundtable_memory()`；`import_memory()` 调用它，整段 try/except；`LOOP_USE_ROUNDTABLE_MEMORY` 默认 `0`；旧三源各加 try/except。
- 验证（smoke test）：
  - a) 开关=0 → `imported-memory.md` 与 baseline **逐字一致**（零回归）；
  - b) 开关=1 且目录存在 → 新节出现、旧节不受影响；
  - c) 删除 `roundtable-memory/` → 不崩溃、旧节完整；
  - d) INDEX 引死链 / LESSONS 节名不匹配 → 标"读取失败"不崩溃。

**Phase 4 — 集成冒烟**
- 非 dry-run 端到端跑完整圆桌；开关置 1 设默认，跑回归圆桌 → PASS。

**最小 smoke test**（kimi 提供，落地脚本 `skills/loop-engine/bin/smoke-roundtable-memory.sh`）：建 baseline → 开关 OFF 必须与 baseline 逐字一致 → 建 `roundtable-memory/` + 开关 ON 验通用铁律/分项目/旧源三者都在 → 清理。

---

## 11. 最小可用格式（模板）

### 11.1 `INDEX.md`
```markdown
# 圆桌记忆索引（INDEX）
> 项目→主题两级。每行：[显示名](相对路径) — YYYY-MM-DD · 一句话结论。链接禁用 [[]]。
## agents
- [loop-engine 圆桌架构](agents/loop-engine-roundtable.md) — 2026-06-24 · 黑板架构圆桌（已实现验证）
## amazon-fba
- （尚无归档）
## finance
- （尚无归档）
## _meta
- [圆桌中立记忆设计](_meta/roundtable-neutral-memory-design.md) — 2026-06-27 · 本系统设计决策与格式约定
```

### 11.2 叶子 `<topic>.md`
```markdown
# 议题标题（一句话）
- **日期**：2026-06-27
- **项目**：agents
- **圆桌会话**：20260627-...
- **状态**：定稿 / 草稿 / 已推翻
- **关联议题**：[xxx](../agents/xxx.md)

## 议题
（要解决什么、为什么开会）
## 结论
（最终结论——agent 召回优先读这里）
## 关键决策
- 决策：……（理由：……）
## 源指针
> 路径以仓库根为基准
- KB 结论：`.roundtable/sessions/<id>/KB/conclusion.md`
- 座位发言：`.roundtable/sessions/<id>/minutes/`
## 历次更新
| 日期 | 圆桌会话 | 变更摘要 |
|------|---------|---------|
| 2026-06-27 | 20260627-... | 初始定稿 |
```

### 11.3 `LESSONS.md`
见 §6.2 + §6.4：`## 通用铁律`（全量召回）+ `## 分项目教训`（按 `### <项目>` 分节）；来源 = 综合席纪要 `## 教训` 节。

### 11.4 `README.md`
```markdown
# 圆桌持久记忆（档案馆）
loop-engine 圆桌的 git 版本化持久记忆。任何 agent 读本目录即可独立获取历史，无需特定 agent 私库。
- INDEX.md — 成果索引（项目→主题）
- <project>/<topic>.md — 叶子：定稿成果
- LESSONS.md — 教训库（通用铁律 + 分项目；开会召回，越跑越稳）
写入纪律：新增教训前先查通用铁律有无同类，有则合并/SUPERSEDED 而非重复新增；前 10 轮后复查条数。
链接一律标准 markdown（无 [[]]、无 frontmatter）。
```

### 11.5 座位纪要 `## 教训` 节（写入端契约 §6.4）
```markdown
## 教训
### 通用
- <一行教训 + 怎么避>（源：<本会现象>）
### agents
- <一行项目专属教训>
```

---

## 12. 待补清单

| 项 | 性质 | 谁来补 |
|---|---|---|
| 座位 brief 改动的具体落点（哪个脚本/模板加 `## 教训` 要求） | 落地 | 执行会 |
| 教训"自动合并/滚动归档" | 后续增强 | 后续会议 |
| 项目名规范短名映射 dict | 后续 | 需要时 |

---

## 13. 验收对照

| 项 | 落点 | 状态 |
|---|---|---|
| #1 中立性自证（两证人） | §9.1 | 闭合 |
| #2 盲点/风险 | §9.2 R1–R17 | 已答 |
| #3 MVP 范围 | §9.3 | 已答 |
| #4 最小可用格式 | §11.1–11.5 | 已答 |
| v2-HIGH① archive 抽取契约 | §6.4 | ✅闭合 |
| v2-HIGH② import 回归 + project id | §7.2 / §8.2 / §10 | ✅闭合 |
| 主人补充：教训库 + 防膨胀 + 改动边界 | §6 / §8.2 / §3 | 已设计 |

---

## 14. 修订史

- **v1**（设计会 `122306` 第1轮 PASS）：骨架 + 成果库 + 中立性（hermes 自证）。
- **v2**（会后并入主人补充）：教训库 `LESSONS.md` + 防膨胀三招 + 归档门槛修正 + kimi 自证回写 + 修 §1↔§8.2 措辞/源指针/`_slug` 瑕疵 + R16。
- **v3**（评审会 `130354` 三轮 BLOCK 揪出 2 HIGH 后）：① 闭合 HIGH① — §6.4 教训来源契约（写入端 `## 教训` 节 + 子标题分类 + 只抽综合席 + hash 去重）；② 闭合 HIGH② — §7.2 project identifier 来源 + §8.2 特性开关默认关/独立函数 try/except/旧源加固 + §10 Phase 0-4 + smoke test；③ §3 加改动边界（数据独立/引擎钩子改 conductor 带护栏）；④ 风险表加 R17，R2/R5 标闭合；⑤ 教训库首批教训纳入评审会 CAP 的两条元教训。
```