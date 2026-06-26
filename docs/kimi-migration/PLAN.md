# Kimi Code 完美承接迁移方案（PLAN）

> 本轮只产出方案，**全程只读**，不执行真实备份或重写。一切"动手"留待方案审定后另起一轮。
> 所有未来产物一律落在**独立的新备份/迁移目录**，与 Claude 原文件物理隔离。
>
> 三项目范围：
> 1. `/Users/melee/Documents/agents`（含 loop-engine 圆桌系统本身）
> 2. `/Users/melee/Documents/amazon-fba-workflow`（含项目自建记忆系统）
> 3. `/Users/melee/Documents/finance`
>
> 文档分工（圆桌）：**执行席（本文作者）主导 A / C / D**；B / E / F 留占位待 **kimi（承接接口实证）** 与 **hermes（结构映射严谨性复审）** 回填后由总指挥综合。

---

## §0 盘点方法与可读边界声明（诚实交代，先读）

本轮执行席在一个**被沙箱+"仅工作目录"安全策略限制**的会话里盘点。可读边界经实测确认如下，**绝不以猜测填充读不到的内容**：

| 区域 | 实测结果 | 本轮处理 |
|---|---|---|
| 工作目录 `/Users/melee/Documents/agents`（项目1，含 loop-engine） | ✅ 完全可读 | 已实测盘点，见 §A.2 |
| `~/.claude/CLAUDE.md`（全局行为准则） | ✅ 全文已在本会话 context（SessionStart 注入），真实内容 | 已盘点，体量待精确 `wc` |
| `~/.claude/projects/-Users-melee-Documents-agents/memory/*`（项目1记忆） | ✅ 内容已在 KB `imported-memory.md`（memory-bridge 真实汇集） | 已盘点，物理文件清单/体量待补 |
| 当前 output-style「拉姆」全文 | ✅ 在本会话 context | 已确认存在；目录内其它风格文件待补 |
| `~/.claude/` 其余子目录（output-styles/ skills/ hooks/ settings*.json） | ❌ `ls` 被"仅工作目录"策略拦；`Read` 需交互授权而本会话无人批准 | **待补盘点项**，见 §A.5，给出补盘命令 |
| `/Users/melee/Documents/amazon-fba-workflow/**`（项目2，含自建记忆系统） | ❌ 同上，读不到 | **待补盘点项**，见 §A.3 / §A.5 |
| `/Users/melee/Documents/finance/**`（项目3） | ❌ 同上，读不到 | **待补盘点项**，见 §A.4 / §A.5 |
| `~/.claude/projects/-Users-melee-Documents-amazon-fba-workflow*/memory/`（含 worktree 子路径） | ❌ 读不到 | **待补盘点项**，归并方案见 §A.3 |
| `~/.claude/projects/-Users-melee-Documents-finance/memory/` | ❌ 读不到 | **待补盘点项** |
| `~/.claude/projects/-Users-melee/`（home 级记忆） | ❌ 读不到 | **待补盘点项** |

**结论**：项目1 与全局行为准则/项目1记忆可据实盘点；项目2、项目3 与 `~/.claude` 多数子目录需在一个**有 `~/.claude` 与 `~/Documents` 只读权限的会话**里跑 §附录的 `00-inventory.sh` 一键补齐。补齐前，下游 §A.3/§A.4 的体量与性质判定均带 `（待补）` 标记，不得当作既定事实执行。

**性质判定四档**：直搬（格式中立，原样可用）/ 需转换（内容可迁、载体或字段需改写）/ 需重写（语义可迁、形态须重做）/ 无对应需替代（Kimi 侧无等价机制，须另行设计）。注：性质的**最终**判定依赖 §B（Kimi 承接接口实证）；本轮给的是**基于资产格式中立性的初判**，标「初判」。

---

## §A 资产全盘点

### A.1 全局共享层 `~/.claude/`（被三项目共用，迁移的"公共底座"）

| # | 资产 | 确切路径 | 体量 | 性质（初判） | 状态 |
|---|---|---|---|---|---|
| A1-1 | 全局行为准则 CLAUDE.md | `~/.claude/CLAUDE.md` | 约 100 行（context 全文估；精确 `wc` 待补）。含 6 大节：业务适配层 / Think Before Acting / Simplicity First / Surgical Changes / Goal-Driven Execution / Knowledge Supersession / 别把幻觉当事实 | 内容直搬，**载体待 §B 定**（Claude 读 CLAUDE.md → Kimi 读什么） | ✅ 已盘点 |
| A1-2 | 输出风格「拉姆」 | `~/.claude/output-styles/<拉姆>.md`（确切文件名待补） | 全文在 context（约 80 行人设协议） | **需重写/无对应需替代**（output-styles 是 Claude 特有机制，Kimi 多半无等价；可降级为"系统提示/persona 文件"） | ⚠️ 确认存在，目录全清单待补 |
| A1-3 | output-styles 目录其余风格 | `~/.claude/output-styles/` | 待补 | 同 A1-2 | 🔲 待补盘点 |
| A1-4 | skills 目录 | `~/.claude/skills/` | 待补（含至少 `agent-reach/`，由记忆确认） | 取决于 Kimi 是否支持 skills（`--skills-dir`？）→ **待 §B**；脚本类直搬、frontmatter 可能需转换 | 🔲 待补盘点 |
| A1-5 | hooks 目录 | `~/.claude/hooks/` | 待补（含至少 `sync-agent-reach-skill.sh`，由记忆确认） | **需转换/需重写**（Claude hooks 由 settings.json 接线；Kimi hook 机制不同） | 🔲 待补盘点 |
| A1-6 | 全局 settings | `~/.claude/settings.json` + `~/.claude/settings.local.json` | 待补 | **需转换**（权限/env/hooks 接线 → Kimi `config.toml` 等价项） | 🔲 待补盘点 |
| A1-7 | home 级记忆 | `~/.claude/projects/-Users-melee/memory/`（推定路径） | 待补 | 内容可搬，frontmatter 私有字段需转换 | 🔲 待补盘点 |

> ⚠️ 注意区分：本会话 system-reminder 列出的大批 skill 名（`superpowers:*` `agent-skills:*` `document-skills:*` `codex:*` 等命名空间者）多为 **plugin 提供**，未必是 `~/.claude/skills/` 下的本地文件；无命名空间者（`agent-reach` `update-config` `verify` `code-review` `loop` `schedule` `init` `review` `security-review` 等）更可能是本地/内置。**本地 skills 的真实清单与 plugin 来源必须由 §附录补盘命令落实**，不在本轮凭名单反推（避免把 plugin 当本地资产误迁）。

### A.2 项目1 —— `/Users/melee/Documents/agents`（含 loop-engine 本身）✅ 已实测

| # | 资产 | 确切路径 | 体量 | 性质（初判） | 状态 |
|---|---|---|---|---|---|
| A2-1 | 仓内 CLAUDE.md | （无） | — | 本仓**无仓内 CLAUDE.md**，行为全靠全局 A1-1 + 项目记忆 A2-9。迁移时须确保 Kimi 侧补上等价项目指令 | ✅ 已确认缺失 |
| A2-2 | loop-engine 本体 | `skills/loop-engine/`（SKILL.md + `bin/`×10 + `tui/tui.py` + `web/{server.py,index.html}` + `templates/`×4） | 164K，18 文件 | **源码直搬**；但座位脚本 `bin/seat-claude.sh` 调 `claude -p`、`seat-kimi.sh`/`seat-codex.sh`/`seat-hermes.sh` 调各自 CLI —— **座位适配层需按"谁主持"重写**（见风险 §F） | ✅ 已盘点 |
| A2-3 | 圆桌活数据（黑板/会话史） | `.roundtable/`（`sessions/*/KB/*`、`minutes/`） | 424K，**gitignored** | 直搬（纯 markdown）；**关键：不在 git 里**，迁移须显式镜像，否则丢失全部圆桌记忆 | ✅ 已盘点 |
| A2-4 | 设计 spec | `docs/superpowers/specs/2026-06-24-loop-engine-design.md` | docs/ 共 20K | 直搬 | ✅ 已盘点 |
| A2-5 | 本轮迁移文档 | `docs/kimi-migration/`（`SMOKE.md` + 本 `PLAN.md`） | 同上 | 直搬 | ✅ 已盘点 |
| A2-6 | 仓内权限白名单 | `.claude/settings.local.json` | 4K，10 条 Bash allow | **需转换**（Claude 权限格式 → Kimi 等价；其中 `claude`/`codex`/`hermes` 相关条目语义随主持方变） | ✅ 已盘点 |
| A2-7 | MCP 配置 | `config/mcporter.json` | 4K（`exa` 一个 server） | 直搬（mcporter 通用，非 Claude 私有） | ✅ 已盘点 |
| A2-8 | 启动器 + 软链 | `roundtable`（仓根脚本，1787B）+ `~/.local/bin/roundtable`（软链，记忆载） | — | 脚本直搬；软链需在 Kimi 侧重建 | ✅ 已确认（软链由记忆佐证，物理 readlink 待补） |
| A2-9 | 项目1记忆 | `~/.claude/projects/-Users-melee-Documents-agents/memory/`（`MEMORY.md` 索引 + 至少 4 文件：`codex-app-slimming.md` `consult-before-building.md` `hermes-agent-coexists.md` `loop-engine-roundtable-project.md`） | 内容已在 KB；物理文件数/体量待 `wc` | 内容可搬；**frontmatter（`node_type`/`type`/`topic`/`originSessionId`/`audit_allow_numbers`）是 Claude 记忆私有 schema → 需转换为 Kimi 记忆形态**（§B） | ✅ 内容已盘点，物理清单待补 |
| A2-10 | venv（运行依赖） | `.venv/`（rich 15.0.0） | gitignored | **不迁**（目标机 `pip install` 重建即可，迁移清单仅记依赖版本） | ✅ 已确认 |

### A.3 项目2 —— `/Users/melee/Documents/amazon-fba-workflow`（含自建记忆系统）🔲 整体待补

本会话**读不到**该仓任何内容（"仅工作目录"策略）。以下为**结构化待补清单**（按预期资产类型列出确切探查路径，内容一律待 §附录补盘命令落实，**不编造**）：

| # | 资产 | 预期路径 | 性质（初判，待证） | 状态 |
|---|---|---|---|---|
| A3-1 | 仓内 CLAUDE.md / AGENTS.md | `amazon-fba-workflow/CLAUDE.md`（及子目录 CLAUDE.md） | 内容直搬，载体待 §B | 🔲 待补 |
| A3-2 | **项目自建记忆系统**（本项目难点） | 位置/格式未知 —— 须深挖：是 `memory/` 目录？`.md`/`.json`/`.sqlite`？有无索引文件？自定义 frontmatter？ | **格式未知 → 性质待定**（可能需重写）。**这是项目2的最高优先补盘项** | 🔲 待补（关键） |
| A3-3 | 源码与配置 | 仓内全部 | 多为直搬，配置需转换 | 🔲 待补 |
| A3-4 | 主仓项目记忆 | `~/.claude/projects/-Users-melee-Documents-amazon-fba-workflow/memory/` | 内容可搬，frontmatter 需转换 | 🔲 待补 |
| A3-5 | **worktree / 多子路径记忆（归并难点）** | `~/.claude/projects/-Users-melee-Documents-amazon-fba-workflow-*/memory/`（每个 worktree 绝对路径 `/`→`-` 各映射一个独立目录）、及子路径会话记忆 | 内容可搬，但**散落多目录须归并去重**（同 topic 跨 worktree 可能分叉，按 CLAUDE.md §5「一 topic 一文件」就地迭代而非并存） | 🔲 待补（关键） |

> **worktree 归并规则（设计已定，待数据落实）**：用 `ls -d ~/.claude/projects/*amazon-fba*` 枚举所有映射目录；按 `name:`/`topic:` 聚类同主题记忆；冲突时取最新 `originSessionId`/git 时序，旧者标 `⚠️ SUPERSEDED`；产出一份**归并后的单一记忆集**进迁移目录，原始多目录原样保真镜像备查。

### A.4 项目3 —— `/Users/melee/Documents/finance` 🔲 整体待补

本会话读不到。结构化待补清单：

| # | 资产 | 预期路径 | 性质（初判，待证） | 状态 |
|---|---|---|---|---|
| A4-1 | 仓内 CLAUDE.md | `finance/CLAUDE.md`（及子目录） | 内容直搬，载体待 §B | 🔲 待补 |
| A4-2 | 源码与配置 | 仓内全部 | 直搬/转换 | 🔲 待补 |
| A4-3 | 项目记忆 | `~/.claude/projects/-Users-melee-Documents-finance/memory/` | 内容可搬，frontmatter 需转换 | 🔲 待补 |
| A4-4 | worktree 记忆（若有） | `~/.claude/projects/-Users-melee-Documents-finance-*/memory/` | 同 A3-5 归并规则 | 🔲 待补 |

### A.5 待补盘点项汇总（补齐 = 跑一次 §附录 `00-inventory.sh`）

> 全部因"会话仅限工作目录"读不到，**非内容缺失**。在一个对 `~/.claude` 与 `~/Documents` 有**只读**权限的会话里跑补盘脚本即可一次补齐。优先级：①A3-2 自建记忆系统格式 ②A3-5 worktree 记忆归并 ③A1-4/5/6 全局 skills/hooks/settings ④A4 finance 全量。

1. `~/.claude/output-styles/` 完整文件清单 + 体量（确认「拉姆」文件名 + 其它风格）
2. `~/.claude/skills/` 本地真目录清单 + 体量 + 区分 plugin 来源
3. `~/.claude/hooks/` 完整清单 + 体量 + 各 hook 在 settings.json 的接线
4. `~/.claude/settings.json` + `settings.local.json` 全文 + 体量
5. `~/.claude/projects/-Users-melee/`（home 级记忆）清单 + 体量
6. 项目1记忆物理文件数/体量（内容已有，补 `wc`/文件名核对）
7. amazon-fba 仓全树（源码/CLAUDE.md/**自建记忆系统格式**）
8. finance 仓全树
9. `~/.claude/projects/*amazon-fba*` 与 `*finance*` 全部映射目录（含 worktree）清单 + 体量
10. `~/.local/bin/roundtable` 软链 `readlink` 验证

---

## §B Claude→Kimi 结构映射 〔占位 · 待 kimi 实证回填〕

> **承接方 kimi 座位**须实证调研（非猜测）Kimi Code 如何加载：项目指令、记忆、skills、hooks、settings、MCP。下表为执行席预置的**待回填骨架**（每行右列待 kimi 填实证结论）：

| Claude 资产 | Claude 载体 | Kimi 对应物（待 kimi 实证） | 直搬/转换/重写/替代 |
|---|---|---|---|
| 项目指令 | `CLAUDE.md`（仓内 + 全局 `~/.claude/CLAUDE.md`） | Kimi 读什么？（`KIMI.md`？`AGENTS.md`？`config.toml` 指针？） | 待定 |
| 项目记忆 | `~/.claude/projects/<映射>/memory/*.md` + frontmatter schema | Kimi 有无路径映射记忆机制？放哪？格式？ | 待定 |
| 输出风格 | `~/.claude/output-styles/*.md` | Kimi 有无 persona/output-style？无则降级系统提示 | 大概率替代 |
| skills | `~/.claude/skills/*/SKILL.md` + 脚本 | Kimi 是否支持 `--skills-dir` / 等价 skill 机制？ | 待定 |
| hooks | `~/.claude/hooks/*.sh` + settings 接线 | Kimi hook 机制（事件名/接线位置）？ | 待定 |
| settings/权限 | `settings.json` / `settings.local.json` | Kimi `config.toml` 等价键 | 转换 |
| MCP | `config/mcporter.json` | Kimi MCP 配置位置 | 大概率直搬 |
| amazon-fba 自建记忆 | 格式待 A3-2 | 取决于其格式与 Kimi 记忆能力 | 待定 |
| loop-engine 座位 | `seat-claude.sh` 调 `claude -p` | Kimi headless CLI 调用方式（`kimi -p`？） | 重写座位适配层 |

---

## §C 备份/迁移目录布局

设计原则：**双层物理隔离**。① Claude 原文件**一字不改**；② 产出分两类落地——
- **保真镜像层**（大、含原始拷贝、不进 git）：落**仓外**独立根目录，完整复刻 Claude 原貌，供回滚与审计。
- **方案/映射/Kimi 形态层**（小、可审、进 git）：落**仓内** `docs/kimi-migration/`，圆桌验证席可直接审。

```
~/Documents/kimi-handover/                      # 仓外保真镜像根（新建，物理隔离，不进任何 git）
├── MANIFEST.md                                 # 总清单：每文件 源路径→镜像路径 + sha256 + 体量 + 性质
├── 00-raw/                                     # 第一层：Claude 原貌【只读拷贝，绝不改】
│   ├── global/                                 # ~/.claude 全局
│   │   ├── CLAUDE.md
│   │   ├── output-styles/                      # 含「拉姆」等
│   │   ├── skills/                             # 仅本地 skills（plugin 不拷，MANIFEST 标注来源）
│   │   ├── hooks/
│   │   ├── settings.json
│   │   └── settings.local.json
│   ├── projects-memory/                        # ~/.claude/projects/<映射>/memory 原样
│   │   ├── -Users-melee/                       # home 级
│   │   ├── -Users-melee-Documents-agents/
│   │   ├── -Users-melee-Documents-amazon-fba-workflow/
│   │   ├── -Users-melee-Documents-amazon-fba-workflow-<worktree-N>/   # 每个 worktree 一目录，原样保真
│   │   └── -Users-melee-Documents-finance/
│   └── repos/                                  # 三仓内 Claude 相关文件（CLAUDE.md/.claude/config 等；源码本身仍在原 git 仓，此处只镜像 Claude 侧承接文件）
│       ├── agents/
│       ├── amazon-fba-workflow/                # 含自建记忆系统原文件
│       └── finance/
├── 01-normalized/                              # 第二层：归并/规整后（仍是 Claude 语义，便于映射）
│   ├── memory-merged/                          # worktree/多子路径记忆按 topic 归并去重后的单一集
│   │   ├── agents/  amazon-fba/  finance/
│   │   └── MERGE-LOG.md                         # 记录每次归并：保留谁、谁标 SUPERSEDED、依据
│   └── inventory.json                          # 机器可读全量盘点（路径/体量/sha256/性质/状态）
└── 02-kimi/                                     # 第三层：Kimi 直接可吃的形态【待 §B 定形后填充】
    ├── agents/  amazon-fba/  finance/          # 每项目：Kimi 项目指令 + 记忆 + skills + settings 的 Kimi 形态
    └── global/                                  # Kimi 全局等价配置

<仓内> /Users/melee/Documents/agents/docs/kimi-migration/   # 方案层（进 git，可审）
├── PLAN.md            # 本文
├── SMOKE.md           # 既有
├── scripts/
│   ├── 00-inventory.sh   # 只读补盘（本轮产出，见 §附录）
│   ├── 10-mirror.sh      # 只读源→只写 00-raw（剧本，待审定后启用）
│   ├── 20-merge.sh       # 00-raw→01-normalized 归并（剧本）
│   └── 30-kimify.sh      # 01-normalized→02-kimi（待 §B 定形）
└── ACCEPTANCE.md      # §E 验收用例（待 kimi 回填）
```

要点：
- `00-raw` 是**只读拷贝**，权限设 `chmod -R a-w` 防误改，保证可回滚到 Claude 原貌。
- plugin 提供的 skills **不进镜像**（非用户资产），MANIFEST 仅登记"来自哪个 plugin"。
- `.roundtable/`（gitignored，424K 圆桌活记忆）**必须显式纳入** `00-raw/repos/agents/`，否则丢失。
- 三层之间**单向**（raw→normalized→kimi），每层产物可独立校验，任一层错不污染上游。

---

## §D 分步执行剧本（可逆 · 可校验 · 每步"只读源 + 只写新目录"）

> 本轮**只产出剧本**，不执行写操作。每步标注前置/校验/回滚。执行须在审定后另起一轮，且删除/覆盖/对外/花钱类一律停下问人。

**阶段 0 —— 补全盘点（唯一允许本轮就跑的，因纯只读）**
- 步 0.1：在有 `~/.claude`+`~/Documents` 只读权限的会话跑 `scripts/00-inventory.sh`，产出 `~/Documents/kimi-handover/01-normalized/inventory.json` 与终端清单。
- 校验：A.5 十项全部由 `🔲` 翻成已确认；amazon-fba 自建记忆系统格式（A3-2）写入文档。
- 回滚：纯只读，无需回滚。

**阶段 1 —— 建保真镜像（只读源 → 只写 `00-raw`）**
- 步 1.1：`mkdir -p ~/Documents/kimi-handover/00-raw/...`（仅新目录）。
- 步 1.2：`cp -Rp`（或 `rsync -a`）逐类拷贝：全局 `~/.claude/{CLAUDE.md,output-styles,skills(本地),hooks,settings*.json}` → `00-raw/global/`；`~/.claude/projects/<各映射>/memory` → `00-raw/projects-memory/`；三仓 Claude 侧文件 → `00-raw/repos/`（**含 agents 的 gitignored `.roundtable/`**）。
- 步 1.3：`chmod -R a-w 00-raw`（锁只读）。
- 校验：对每文件算 `sha256` 写入 `MANIFEST.md`，与源比对一致；`diff -r` 源与镜像零差异。
- 回滚：`rm -rf 00-raw`（只删新目录，源未动）。**红线：本阶段对源仅 `cp`/`sha256sum`/`diff`，零写。**

**阶段 2 —— 归并规整（`00-raw` → `01-normalized`，源已不参与）**
- 步 2.1：枚举 `~/.claude/projects/*amazon-fba*`、`*finance*` 全部映射目录，按 `name`/`topic` 聚类。
- 步 2.2：同 topic 跨 worktree 冲突 → 取最新，旧者拷入并标 `⚠️ SUPERSEDED`，写 `MERGE-LOG.md`（CLAUDE.md §5 就地迭代）。
- 步 2.3：产出 `memory-merged/<项目>/` 单一记忆集 + `inventory.json`。
- 校验：归并集无重复 `name`；每条 SUPERSEDED 有依据；记忆总条数 = 去重后应得数（人工抽审 MERGE-LOG）。
- 回滚：`rm -rf 01-normalized`（`00-raw` 与源均不动）。

**阶段 3 —— Kimi 形态转换（`01-normalized` → `02-kimi`）〔待 §B 定形〕**
- 步 3.1：按 §B 实证的 Kimi 载体，把项目指令/记忆/skills/settings 转成 Kimi 形态。
- 步 3.2：座位适配层 `seat-claude.sh` → Kimi headless 调用重写（loop-engine 可在 Kimi 主持下跑）。
- 校验：见 §E 验收用例。
- 回滚：`rm -rf 02-kimi`。

**阶段 4 —— 验收（§E）**：在 Kimi Code 冷启动三项目各一，复现一个典型任务。

---

## §E 验收标准（"完美承接"客观验证）〔占位 · 待 kimi 回填可执行用例〕

骨架（待 kimi 把"读到什么文件=通过"填实证）：
- [ ] 冷启动 agents：Kimi 读到等价项目指令（全局准则+项目记忆），能复现"开一次圆桌冒烟"。
- [ ] 冷启动 amazon-fba：Kimi 读到归并后的项目记忆 + 自建记忆系统等价承接，复现一个该项目典型任务。
- [ ] 冷启动 finance：同上。
- [ ] 记忆无丢失：`02-kimi` 记忆条数 ≥ 归并集条数；抽样内容逐字一致。
- [ ] skills/hooks：迁移后的 skill 在 Kimi 可触发（或明确标注 Kimi 无对应、已降级替代）。

## §F 风险与未知〔占位 · 待 hermes 复审补强；执行席先列已确定项〕

执行席已能确定的风险（hermes 请挑刺补充）：
1. **路径映射陷阱**：worktree 各自映射独立 `projects/<映射>/memory`，漏枚举 = 丢记忆；目录名是绝对路径 `/`→`-`，路径含特殊字符时映射可能不直观。
2. **gitignored 活记忆丢失**：agents 的 `.roundtable/`（424K 圆桌历史）不在 git，常规"clone 仓库"迁移会整丢，必须显式镜像。
3. **记忆私有格式**：Claude memory frontmatter（`node_type`/`topic`/`originSessionId`/`audit_allow_numbers`）+ amazon-fba **自建记忆系统**格式未知，Kimi 无对应字段时转换有信息损耗。
4. **output-styles 无对应**：「拉姆」persona 若 Kimi 无 output-style 机制，需降级为系统提示，行为可能漂移。
5. **plugin vs 本地 skills 混淆**：误把 plugin skills 当用户资产迁移 = 既冗余又可能版本冲突。
6. **座位适配层耦合**：loop-engine 座位脚本硬编码 `claude -p`/`codex`/`hermes` CLI，Kimi 主持需重写，否则圆桌跑不起来。
7. **本轮盘点盲区**：项目2/3 与 `~/.claude` 多数子目录未实测（§A.5），性质判定是初判，执行前必须先跑阶段 0 补全，否则可能基于错误前提迁移。

---

## §附录 · `scripts/00-inventory.sh`（只读补盘脚本，本轮产出）

纯只读（仅 `ls`/`find`/`du`/`wc`/`sha256sum`/`cat`），不改任何 Claude 文件。在有 `~/.claude`+`~/Documents` 读权限的会话跑，补齐 §A.5。脚本见 `docs/kimi-migration/scripts/00-inventory.sh`。
