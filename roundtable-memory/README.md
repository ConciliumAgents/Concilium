# 圆桌持久记忆（档案馆）

loop-engine 圆桌的 **git 版本化**持久记忆。任何 agent（claude / hermes / kimi / …）clone 仓库后读本目录即可独立获取历史，无需特定 agent 的私库。

- `INDEX.md` — 成果索引（项目 → 主题两级）
- `<project>/<topic>.md` — 叶子：某议题历次圆桌的定稿成果
- `LESSONS.md` — 教训库（通用铁律 + 分项目；开会召回，越跑越稳）

## 由谁写

conductor 散会时 `archive_to_memory()`（`skills/loop-engine/bin/conductor.py`）自动追加：
PASS 成果落 `<project>/<topic>.md` 叶子并更新 `INDEX.md`；各会综合席纪要的 `## 教训` 节落 `LESSONS.md`。
人也可手改叶子，作下一轮圆桌的输入。

## 写入纪律（防膨胀，靠纪律非自动魔法）

- 新增教训前先查 `## 通用铁律` 有无同类，有则**合并 / 标 `SUPERSEDED`** 而非重复新增。
- 通用铁律刻意保持小而收敛；约定**前 10 轮后复查条数**，过时的标 `SUPERSEDED`、量大滚动到 `LESSONS-archive/`（后续）。
- 单项目节随会议次数线性增长属已知边界，MVP 可接受。

## 格式铁律（非-Claude 座位零打折，两证人已确认）

- 链接一律标准 markdown `[显示名](相对路径)`，**禁 `[[]]`**。
- **不用 frontmatter**；元数据放标题下 kv 列表。
- **不依赖 `/→-` 路径映射**，用项目名。
- 源指针**以仓库根为基准**书写。
- 叶子文件名（topic）由 `_slug()` 生成，**保留 CJK**；若环境对 CJK 文件名不友好，落地可加 ASCII fallback（见 spec §9.2-R15）。
