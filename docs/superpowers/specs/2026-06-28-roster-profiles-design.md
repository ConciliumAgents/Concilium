# 座位画像设计草案 v2 —— 给主持人派活一份「实战依据」

> 状态：草案 v2（一轮异构轻审收敛，准备实现）
> 日期：2026-06-28
> 起因（用户洞察）：圆桌让主持人(claude)分活+把控会议，但**主持人派活的唯一依据是 `roster.md` 的静态 `strength`**——`roster-detect.py` 硬编码的"出厂标称"，**粗**且**会失真**（标 codex"强编码"实则连不上、标 claude 适合"核心活"实则揽 exec 超时）。主持人需对每个模型的**实战了解**才有派活依据。
> 评审历程：v1 → hermes BLOCK(2 HIGH：kimi 画像事实错误、LESSONS 迁移剪裁线模糊) / kimi PASS(MEDIUM：画像环境瞬态偏见、加时间注记) → v2 收敛。见 §9。

---

## 1. 问题

派活依据链现状：`roster-detect.py` 探测 → 每座位静态 `strength` → `write_roster()` 写 `KB/roster.md` → 主持人 plan"读 roster.md，按特长派活"。缺口：`strength` 是出厂标称，不反映实战（谁快谁慢、谁严谁松、谁有坑），实战观察散落对话/LESSONS，主持人开会读不到。

---

## 2. 目标与非目标

**目标**：给主持人一份**手动维护、可读的座位实战画像**作为派活/选席依据。
- 主持人 plan 时能读到每座位的实战表现、适合角色、坑。
- 画像可随圆桌**手动**积累更新（MVP 不做自动）。

**非目标（留 §7）**：自动画像生成（从纪要提炼）；画像驱动的自动派活（仍由主持人 LLM 据画像判断，不做硬规则）；让验证席也按画像调严格度。

---

## 3. 方案

### 3.1 载体：`roundtable-memory/ROSTER-PROFILES.md`

放 `roundtable-memory/`（进 git、纯 markdown、中立，与 INDEX/LESSONS 并列）。**文件头固定 caveat**（防偏见，hermes/kimi 共识）：

```markdown
# 座位实战画像（ROSTER-PROFILES）
> ⚠ 画像基于少量实战，是**当前倾向**非永久标签；随新证据手工更新。
> 这是**项目/环境级观察**：连接类失效（如 codex）是环境瞬态，带日期/环境限定，勿当模型永久属性。
> 维护：散会后由人工/主持人更新对应座位节（见各节「更新于」）。
```

每座位一节，维度（**去掉"出厂特长"字段**——避免抄 roster-detect 造两处真相；出厂层已在 roster.md 工厂层）：

```markdown
## <seat> (<模型>, <血统>) · 更新于 <date>
- 实战画像：<速度/性格/真实表现，写"当前倾向"，标样本量>
- 适合角色：<plan / exec / review / 异质复审 …>
- 坑：<已知失效模式/注意事项，环境类加日期限定>
```

### 3.2 接线：合并进 `roster.md`（不走记忆桥、无开关、零回归）

画像**不**走 roundtable-memory 的 `_roundtable_memory()` 召回——那受 `LOOP_USE_ROUNDTABLE_MEMORY`（默认关）控制，默认关时主持人读不到。改为：

- `write_roster()`（`conductor.py`，无开关无条件调用）写 `KB/roster.md` 时**额外读 `ROSTER-PROFILES.md`**，按座位名匹配，把"实战画像/适合/坑"并进该座位节。
- 主持人 plan 本就读 roster.md → **无需新召回、无需开关、零回归**。
- **解析失败整体回退**（hermes/kimi 共识）：文件不存在/格式坏 → **整份跳过、不半合并**（避免部分座位有画像部分没有的错乱），roster.md 退化为纯出厂层；except 块内 `reporter.log()` 一行说明（否则无声跳过难排障）。

### 3.3 初始画像（去绝对化 + 时间/环境注记）

- **claude (Opus, Anthropic) · 更新于 2026-06-28**：实战=握全上下文/规划综合强；**不适合 exec**（headless 大任务易撞 600s 超时空转，本轮执行会 5 轮 claude-exec 全 0 字节）；适合=总指挥(plan)+验证席(review，纯脑只读)；坑=大块核心代码走主对话带外亲写，勿进圆桌 exec 座位。
- **hermes (DeepSeek, 异质) · 更新于 2026-06-28**：实战=执行快有产出；**主观"是否充分"的复审偏宽松**（曾"修复成立"即放行），但**硬事实/代码核对很严**（本轮逮出 kimi 画像 600s 事实错误）；适合=执行席、异质复审；倾向=综合时与深挖型(kimi)交叉验证。（样本少）
- **kimi (K2.7, Moonshot, 异质) · 更新于 2026-06-28**：实战=深挖未覆盖边界的能力强（多轮 spec 评审屡中）、快、能扛大活（单纪要曾 173KB）；适合=严格验证席、核心执行、异质复审；坑=headless 输出冗长（thinking 外泄）；**圆桌内受 `LOOP_SEAT_TIMEOUT`=600s 约束，大活接近该线会被 rc=124 截断**（注：脱离圆桌直调无此超时）。（样本少）
- **codex (GPT, OpenAI) · 更新于 2026-06-28**：实战=**截至 2026-06-28 本环境探测 chatgpt.com 后端 `websocket tls handshake eof`、连接失败，暂不可用**（环境瞬态，非永久属性，复测可更新）；现已入 EXEC_EXCLUDE 仅验证；坑=不可用时勿派活。

### 3.4 LESSONS 迁移（三层剪裁明确，hermes HIGH）

`LESSONS.md` 现那条长 bullet 绞了三层，按下表归位：

| 层 | 内容 | 去向 |
|---|---|---|
| ① 原则 | 主持人派活/选席须基于**实战画像**而非静态 strength | **留 LESSONS** |
| ② 战术 | 异质复审优先、综合以深挖型为主+交叉验证、异质血统利于复审 | **留 LESSONS**（是"如何选席"的 cross-cutting 编排原则，非画像数据） |
| ③ 具体画像 | claude 揽 exec 超时 / hermes 偏宽松 / kimi 深挖 | **迁 PROFILES** |

迁移后 LESSONS 那条收敛为：「主持人派活/选验证席须基于各模型**实战画像**（非仅静态 strength）；异质复审优先、综合以深挖型为主+异质交叉验证。**→ 各座位具体画像见 `roundtable-memory/ROSTER-PROFILES.md`**」（含**显式指针**，hermes 建议）。"审真代码>审spec"那条独立保留不动。

### 3.5 主持人 prompt 引导用画像（hermes MEDIUM）

`seat-claude.sh`/`seat-kimi.sh` 的 plan prompt 现说"读 KB/roster.md（各 agent 的**特长**花名册）"——只引向出厂特长。改为"读 KB/roster.md（各 agent 的**特长与实战画像/适合/坑**），**据实战画像选席派活**"。否则画像进了 roster.md 主持人也可能略过。

### 3.6 积累流程（MVP 手动，承认落差）

- 谁写：散会后人工/主持人更新对应座位节 + `更新于`。**无任何自动组件写 PROFILES**（plan 只读、exec 写 state.md、archive 只写 INDEX/LESSONS）——目标语言据此调为"**手动维护**"，半自动提级 §7。
- 纪律：同 LESSONS，新增前看该座位已有画像，合并/更新勿堆叠矛盾；保持精炼。
- 防回灌：座位 exec 的"## 教训"经 archive 进 LESSONS，**勿在教训里写画像内容**（否则绕过手动维护回灌），画像只手动进 PROFILES。

---

## 4. 受影响文件

| 文件 | 改动 |
|---|---|
| `roundtable-memory/ROSTER-PROFILES.md` | 新建：文件头 caveat + 四座位初始画像（§3.1/3.3） |
| `conductor.py` `write_roster()` | 读 PROFILES 按座位合并进 roster.md，解析失败整体回退+log（§3.2） |
| `roundtable-memory/LESSONS.md` | 那条按三层归位：留原则+战术+指针，迁出具体画像（§3.4） |
| `seat-claude.sh`/`seat-kimi.sh` | plan prompt 引导据画像选席（§3.5） |

不碰：roster-detect.py（出厂层不变）、记忆桥/召回开关、座位 exec/review 主体。

---

## 5. 验收标准

1. `KB/roster.md` 每座位节含实战画像/适合/坑（出厂层仍由 roster-detect 提供）。
2. 主持人 plan 能据画像派活（不把 exec 派 claude、严审优先 kimi）——观察一轮 plan 输出。
3. **零回归**：`ROSTER-PROFILES.md` 不存在/格式坏 → `write_roster` 不崩、**整体回退**为纯出厂层、log 一行。
4. 不依赖 `LOOP_USE_ROUNDTABLE_MEMORY` 开关（默认即生效）。
5. LESSONS 不再列具体画像（只留原则+战术+指针），PROFILES 为画像唯一真相，无重复。
6. 画像均带 `更新于` + "当前倾向/样本少"措辞，codex 带日期/环境限定。

---

## 6. 风险与取舍

- **画像固化偏见**（核心风险，两家共识）：单次表现当永久标签。缓解=文件头 caveat + "当前倾向"措辞 + `更新于` + 环境类加日期限定 + 随证据更新。**本轮活例**：曾把"hermes 宽松"当标签，本轮 hermes 却最严还逮出硬错误 → 画像已改"主观判断偏松但硬事实核对严"。
- **环境瞬态偏见**（kimi）：连接失败（codex）写死会雪藏可用座位 → 带日期/环境限定。
- **积累靠人**（hermes）："持续积累"实为"人工记得更新"，滞后则画像陈旧 → 目标已调"手动维护"，半自动留 §7。
- **跨项目漂移**（kimi）：画像是项目/环境级观察 → 文件头注明。
- roster.md 变长：每座位多几行，无害。

---

## 7. 下一阶段

- 半自动画像：散会从 minutes 提炼表现，提示主持人确认后更新（hermes 建议提级——无自动积累则画像会过时）。
- 画像按任务类型细分（写代码 vs 评审 vs 调研）。
- 验证席也参考画像调严格度。

---

## 8. 评审账（v1 → v2）

hermes BLOCK(2 HIGH) / kimi PASS。收敛：

| 发现 | 来源 | 级别 | v2 处理 |
|---|---|---|---|
| kimi 画像"11分钟无超时"事实错误（圆桌内 600s 强杀） | hermes | HIGH | §3.3 改"受 600s 约束、大活被截断" |
| LESSONS 迁移剪裁线模糊（原则/战术/画像三层绞一起） | hermes | HIGH | §3.4 三层归位表 + 显式指针 |
| 主持人 prompt 只引向"特长"、不读画像 | hermes | MEDIUM | §3.5 prompt 引导据画像选席 |
| 初始画像太绝对、样本少固化偏见 | hermes+kimi | MEDIUM | §3.1 caveat + §3.3 去绝对化/加注记 |
| codex"不可用"环境瞬态写死会雪藏座位 | kimi | MEDIUM | §3.3 加日期/环境限定 |
| 解析失败应整体回退不半合并 | hermes+kimi | MEDIUM | §3.2 整体回退+log |
| "持续积累"无机制、全靠人 | hermes | MEDIUM | §3.6 调"手动维护"、§7 提级半自动 |
| 出厂 strength 在 PROFILES 抄一遍（两处真相） | hermes | LOW | §3.1 去掉"出厂特长"字段 |
| 防画像回灌 LESSONS | kimi | LOW | §3.6 防回灌一句 |
