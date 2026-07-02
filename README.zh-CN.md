# Concilium

[English](README.md) | 简体中文

> 维护说明：`README.md` 是权威版本；本中文版应随英文 README 同步更新。

把真实的本地 AI agent 作为可审计的圆桌来运行。

[快速开始](#快速开始) | [核心概念](#核心概念) | [安全与隐私](#安全与隐私) | [从源码运行](#从源码运行) | [参与贡献](#参与贡献)

## Concilium 是什么

Concilium 是一个本地开发者工具，用来协调多个 agent CLI。它不会要求一个模型假装成一个团队，而是把任务路由给你机器上真实安装的本地席位，例如 Claude Code、Codex CLI、Hermes 或 Kimi。运行后，Concilium 会记录请求内容、执行 lane、参与席位、检查结果，以及本次运行如何收束。

## 为什么需要它

单 agent 工作流很快，但在较大的变更里不总是容易信任：

- agent 的假设可能不可见。
- 执行和复审经常混在一起。
- 失败有时会被一个漂亮的最终回复掩盖。
- 很多多 agent 演示会合并观点，却没有证明哪些 agent 真的运行过。

Concilium 把 agent 工作当作一项需要路由、容量检查、执行边界和证据的操作来处理。目标很简单：在你信任结果之前，你应该能看见它是怎样产生的。

## 亮点

- 探测本机可用的 agent 席位。
- 通过 fast execution、review、audit、plan review、roundtable review 等 lane 路由任务。
- 在真实执行前运行 Budget Guard，让额度缺失、容量未知或高风险席位选择变得可见。
- 启动本地 service/API，供工具检查状态或运行历史。
- 为完成的运行写入机器可读的 run summary。
- 默认把敏感运行产物留在本地。

## 工作方式

```text
task
  -> route selection
  -> seat and capacity check
  -> lane execution
  -> tests or review gates
  -> run-summary.json
```

顶层 `roundtable` launcher 是主要 CLI 入口。大部分运行时代码位于 `skills/loop-engine/bin`。`loop-engine` 是 Concilium runtime 的历史目录名；在工具预览阶段保留它，是为了避免破坏现有脚本、测试和本地工作流。当你需要 API 访问或当前 Debug Console 时，可以运行 `roundtable service` 启动本地服务。

## 快速开始

前置条件：

- Python 3.11 或更新版本。
- `git` 和 `ripgrep`。
- 如果要运行真实席位，需要至少一个已安装并已登录的本地 agent CLI。

```bash
git clone https://github.com/ConciliumAgents/Concilium.git
cd Concilium

./roundtable --version
./roundtable --doctor

python3 skills/loop-engine/bin/concilium-run.py \
  --repo "$PWD" \
  --task "Preview a README review route without calling live seats." \
  --test-cmd "true" \
  --dry-run

./roundtable service --no-open
```

快速开始先使用 dry-run 命令。调用真实席位的命令可能消耗模型服务额度，也依赖你的本地 agent 订阅和登录状态。

## CLI 速查

```bash
./roundtable --version          # 显示 launcher、仓库、分支和 commit。
./roundtable --doctor           # 探测可用的本地席位。
./roundtable --task "..."       # 运行一个路由后的 Concilium 任务。
./roundtable service --no-open  # 启动本地 service/API，不自动打开浏览器。
```

## 核心概念

**Seat**

Concilium 可以调用的本地 agent CLI，例如 Claude Code、Codex CLI、Hermes 或 Kimi。席位是否可用取决于你的机器环境。

**Lane**

带有特定意图的执行模式，例如快速实现、复审、审计或圆桌式交叉检查。

**Budget Guard**

真实执行前的预检，用来暴露席位可用性和容量风险。

**Run Summary**

运行结果的机器可读记录。对于已完成的运行，`run-summary.json` 是稳定状态来源。

**Local Service**

用于检查状态和运行本地工作流的 localhost API/debug surface。它不是托管服务。

## 按目标阅读文档

| 目标 | 从这里开始 |
|---|---|
| 了解项目 | `README.md` / `README.zh-CN.md` |
| 理解 agent-level MoA | `docs/loop-engine/agent-moa-positioning.md` |
| 学习席位输入/输出规则 | `docs/loop-engine/seat-contract.md` |
| 发布或更新 public mirror | `docs/maintainers/public-release-workflow.md` |
| 报告安全问题 | `SECURITY.md` |
| 贡献 patch | `CONTRIBUTING.md` |

## 支持的 Agent

Concilium 围绕真实的本地 CLI 设计。具体 roster 取决于你机器上安装并登录了哪些工具。

运行：

```bash
./roundtable --doctor
```

查看当前可用席位。

## 安全与隐私

Concilium 默认把运行证据视为本地且敏感的数据。

- `.roundtable/sessions/**` 可能包含任务上下文、本地路径、测试输出和席位 transcript。
- 不要公开原始 provider 日志、凭证、私有 memory 或未清洗的运行产物。
- 在新机器上运行真实执行前，优先使用 dry-run 或 review-only 工作流。
- 在公开 issue、pull request 或 demo 中分享生成产物前，请先人工复查。

## 项目状态

Concilium 目前适合作为本地 CLI 和 service 工作流的开发者预览工具。它不是托管平台，也不是面向终端用户的完整产品。

当前重点是可靠性、清晰的执行边界、可复现的本地设置，以及安全可运行的公开示例。

## 从源码运行

运行测试：

```bash
python3 -m unittest discover -s skills/loop-engine/tests -p 'test_*.py'
git diff --check
```

## 参与贡献

欢迎提交 bug 报告、文档修复、可复现的设置说明，以及小范围 runtime patch。提交 pull request 前请阅读 `CONTRIBUTING.md`。

安全敏感问题或意外 secret 暴露请遵循 `SECURITY.md`，不要在公开 issue 中包含私有日志或凭证。

## 社区

- 对可复现 bug 或文档缺口，请开 issue。
- 设置和支持问题请先清洗内容：不要包含原始 transcript、provider token、本地账号数据或私有 memory。
- Pull request 应包含用于验证变更的命令输出或证据。

## License

MIT
