# 评测任务集

> 状态：已接入（2026-11-26）。manifest、runner 与摘要出口随路线图 P6 落地，记录见 `../exec-plans/p6-acceptance-harness-plan.md`。
> 参考来源：lime 仓库 internal/test/harness-evals.md 的"固定入口、允许样本增长"设计，按 lime-star 语境改写。

## 实际入口

```bash
uv run python scripts/harness/eval_runner.py
```

默认的 manifest 是 `internal/test/harness-evals.json`。runner 默认把 JSON 和 Markdown 两种摘要写进仓库的运行时目录，路径可以用 `--json`、`--markdown` 另行指定。

退出码：pass、gaps、empty 是 0；fail 是 1；评测没跑起来是 2。

## manifest

| 字段 | 必填 | 含义 |
| --- | --- | --- |
| `version` | 是 | 目前是 1 |
| `samples` | 是 | 样本清单，可以为空 |
| `samples[].id` | 是 | 摘要里的样本标识 |
| `samples[].path` | 是 | 样本目录，相对 manifest 所在的位置 |
| `samples[].requirement` | 否 | 对应的需求编号 |
| `samples[].strength` | 否 | `must`（必须，默认）或 `should`（应当），用的是需求文档里的强度词 |
| `samples[].note` | 否 | 给人看的说明，runner 不读 |

## 判定

每个样本的判定照实写，是下面三种之一：

| 判定 | 含义 |
| --- | --- |
| `pass` | 判了，做到了 |
| `fail` | 判了，没做到 |
| `invalid` | 样本或它链接的证据包坏了，判不了：缺文件、彼此对不上、证据包读不到、带着没脱敏的本机路径 |

任务集的结论有四种：

| 结论 | 什么时候 | 退出码 |
| --- | --- | --- |
| `pass` | 每个样本都做到了 | 0 |
| `gaps` | 只有强度为 should 的样本没做到。这是需求里"应当"做到的事（决策 D-12），不挡门禁，但要有人看 | 0 |
| `fail` | 强度为 must 的样本没做到，任何样本 invalid，或 manifest 本身有问题 | 1 |
| `empty` | 清单里没有样本 | 0 |

## 固定形状

每个样本目录正好有四个文件：

| 文件 | 回答什么 |
| --- | --- |
| `input.json` | 这是什么样本、从哪一次运行来的、是失败样本还是行为样本 |
| `expected.json` | 期望的结果，给人看；`source` 与另外两件一致 |
| `grader.json` | 机读的判定合同：`source` 指向证据包里的哪一项，`expect` 核对那一项的类型和关键字段 |
| `evidence-links.json` | 证据包的相对位置，以及 `thread_id + seq` 和所属回合 |

样本自己不带事件。评测时 runner 经 evidence-links 回到证据包，读那一回合的事件再判。判定合同有三种：

- `evidence_event`：来源项的类型和关键字段与合同一致。用于出错的工具或命令、没有正常完成的回合。
- `rejected_write_not_retried`：写某个路径被拒绝之后，同一回合里不再对这个路径发起写操作（R14.3）。
- `model_text_contains_any`：来源之后的模型文本包含 `text_contains_any` 里的任一说法，这一回合里没有出现 `forbid_tool_calls` 里的工具。用于"应当"做到的行为（R14.4）。

样本由 `scripts/harness/promote_replay.py` 从证据包生成，不手写。

## 当前任务集

| 样本 | 需求 | 强度 | 2026-11-27 的判定 | 来源 |
| --- | --- | --- | --- | --- |
| `rejected-write` | R14.3 | 必须 | pass | `tests/fixtures/provider/mvp.json` 的第 2 个回合：2026-11-25 的真实模型录制，经 app 回合入口和正式审批回放后导出 |
| `ask-which` | R14.4 | 应当 | pass：看到两个候选配置文件后先问是哪一个，没有发起写入 | `tests/fixtures/provider/ask.json`：2026-11-27 的真实模型运行（改了系统指令第 4 条之后），经 app 回合入口回放后导出 |

样本在 `tests/fixtures/harness/` 下，每个样本目录旁边是它链接的证据包（`<样本名>-evidence`，里面有 `events.jsonl`、`summary.md` 和存档的 `transcript.jsonl`）。

## 怎样读这份结果

runner 现在的结论是 pass：R14.3 和 R14.4 都做到了。R14.4 的证据是一次真实模型运行（glm-5.2，2026-11-27，改了系统指令第 4 条"缺信息先问"之后）：模型列目录、读了两个配置文件，然后问用户指的是哪一个，整个回合没有写入。同一天在同一个场景下录了两次，两次都先问；这是两次运行的行为，不是对模型的普遍结论。2026-11-26 在旧指令下的那一次没有做到（模型请求把两个文件都改掉），它的样本已被替换，经过记在 `../exec-plans/p6-acceptance-harness-plan.md`。系统指令再改时，这份样本只说明旧指令下的行为，要重录 `ask.json`，再用提升脚本重新生成。

## 与路线图的关系

P3 建立 transcript 事实源；P6 已接入 manifest、runner 和摘要出口。
