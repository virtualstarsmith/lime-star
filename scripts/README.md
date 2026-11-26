# scripts/ — 治理脚本目录

本目录是**冻结基线目录**：根目录文件与一级领域子目录由 `governance/scripts-baseline.json` 冻结，新增脚本必须进入既有领域子目录，不允许散落在根目录。此规则由 `check-scripts-baseline.mjs` 机械执行。

治理脚本只做治理检查，不写业务逻辑；`scripts/harness/` 是路线图 P6 的反馈层工具链。产品代码是 Python。

## 脚本清单

| 脚本 | 作用 | 用法 |
| --- | --- | --- |
| `verify-local.mjs` | 默认本地门禁编排器：按改动路径增量选任务，fail-fast | `node scripts/verify-local.mjs [--full] [--dry-run] [--only a,b]` |
| `check-file-size-governance.mjs` | 行数棘轮：新文件超过 800 行违规，超过 1000 行硬违规；基线文件只许收缩 | `node scripts/check-file-size-governance.mjs [--root <dir>] [--update]` |
| `check-scripts-baseline.mjs` | scripts 目录冻结基线与垃圾产物检查 | `node scripts/check-scripts-baseline.mjs [--root <dir>] [--update]` |
| `check-contracts.mjs` | 契约同步门禁：schema 变更必须同步消费者并显式确认 | `node scripts/check-contracts.mjs [--root <dir>] [--update]` |
| `check-doc-links.mjs` | 文档交叉引用守卫：规则、计划、手册之间的相对引用不许断链；带目录的引用必须按路径在仓库内找到，只有裸文件名可按文件名全树查找 | `node scripts/check-doc-links.mjs [--root <dir>]` |
| `scripts/security/check-secrets.mjs` | 密钥守卫：`.env` 必须被 Git 忽略且不被跟踪；已跟踪文件里不得出现常见格式的密钥。报出位置和规则名，不回显密钥 | `node scripts/security/check-secrets.mjs [--root <dir>]` |
| `scripts/smoke/agent_gate_b.py` | Gate B 冒烟（Python，路线图 P4）：在真实进程里跑 MVP 主场景，对着会话记录和磁盘断言；默认回放录制的夹具，不联网 | `uv run python scripts/smoke/agent_gate_b.py [--live]` |
| `scripts/smoke/resume_gate_b.py` | 恢复的 Gate B 冒烟（Python，路线图 P5）：六个真实的 lime-star 进程先后在同一个工作目录里运行，其中一次在批准提示处被强制结束，之后的进程带 `--resume`；对着会话记录、请求日志和磁盘断言。默认回放录制的夹具，不联网 | `uv run python scripts/smoke/resume_gate_b.py [--live]` |
| `scripts/harness/export_evidence.py` | 证据导出（Python，路线图 P6）：读一份会话记录，导出逐事件的 JSON Lines 和 Markdown 摘要，每条事件带 `thread_id + seq`；最后一个回合没有结局时用 thread_store 的读模型判为中断，不写回记录 | `uv run python scripts/harness/export_evidence.py --transcript <file> --out <dir>` |
| `scripts/harness/promote_replay.py` | 样本提升（Python，路线图 P6）：从证据包生成 input、expected、grader、evidence-links 四件回放样本；样本不带事件，本机绝对路径换成占位路径 | `uv run python scripts/harness/promote_replay.py --evidence-dir <dir> --case-dir <dir> --case-id <id> --seq <n>` |
| `scripts/harness/eval_runner.py` | 评测 runner（Python，路线图 P6）：读固定 manifest 和回放样本，回到证据包去判，输出结论一致的 JSON 与 Markdown 摘要 | `uv run python scripts/harness/eval_runner.py [--manifest <file>] [--json <file>] [--markdown <file>]` |

治理脚本零依赖（Node 18 或更高），必须在**仓库根目录**运行，违规时退出码非零。冒烟脚本是 Python，经 uv 运行，不属于治理脚本；两个冒烟脚本共用的小工具在 `tests/integration/smoke.py`，它们也借用 tests 里驱动真实进程和回放的小工具。Python 工具脚本都在 mypy 的检查范围里（pyproject.toml 的 files 含 scripts）；verify-local 的 lint、typecheck 任务由 `scripts/smoke/` 和 `scripts/harness/` 的改动触发。harness 脚本只消费 transcript 或其派生物，不参与产品运行时。评测 runner 的结论是 fail 才让门禁失败；gaps（应当做到而没做到）的退出码是 0，必须写进收尾报告。

## 接入状态

lime-star 已于 2026-11-23 完成接入，记录见 `internal/exec-plans/paradigm-port-plan.md`。当前基线：根文件 6 个（5 个脚本加 README），一级目录 3 个：security（路线图 P1 建立，记录见 `internal/exec-plans/p1-chat-plan.md`）、smoke（路线图 P4 建立，记录见 `internal/exec-plans/p4-tools-approval-plan.md`）和 harness（路线图 P6 建立，记录见 `internal/exec-plans/p6-acceptance-harness-plan.md`）。

三个基线文件都在 `governance/` 下，属于**必须提交**的版本化文件：

- `governance/scripts-baseline.json`：scripts 目录结构快照。结构变化后需要 `--update`，并在计划中说明理由。
- `governance/file-size-baseline.json`：超过 800 行文件的行数棘轮；只在拆分完成或明确登记退出条件时收缩式更新。
- `governance/contracts.json`：契约清单，人工维护。`governance/contracts-state.json`：schema 哈希，由 `--update` 生成。

## 路线图新增的目录

路线图分阶段新增三个一级目录：security（P1，密钥守卫，已建立）、smoke（P4，Gate B 冒烟，已建立）、harness（P6，证据导出与评测，已建立）。每次新增都必须在该阶段的执行计划里写明理由，再运行 `node scripts/check-scripts-baseline.mjs --update`。

## 守卫脚本的回归用例

治理脚本自己也要有仓库内的回归。用例放在 `tests/integration/` 下，文件名以 `test_guard_` 开头：在临时目录里运行真实的脚本进程，断言退出码和输出。verify-local 的任务 test:guards 在 scripts/ 或这些用例变动时执行它们。

Harness 反馈层的合同守卫在 `tests/integration/test_harness.py`：证据包里的项与会话记录逐项一致、回放样本回到证据包去读。它由 test:harness 任务执行，摘要出口由 harness:eval 任务执行。

## 架构守卫

依赖方向和重大架构变更的确认块没有对应的治理脚本，直接写成 pytest 用例：`tests/integration/test_guard_architecture.py`。它检查仓库自身，不启动进程。verify-local 的 architecture 任务在产品代码（`src/lime_star/`）、架构图（`internal/aiprompts/architecture.md`）或这个文件变动时执行它。依赖矩阵从架构图第 4 节的表里读，架构图是唯一来源。

## 重新生成基线

```bash
node scripts/check-scripts-baseline.mjs --update
node scripts/check-file-size-governance.mjs --update
node scripts/verify-local.mjs --dry-run
```

## 契约清单格式

`governance/contracts.json` 的格式示例（lime-star 的第一条真实契约 thread-items 已于路线图 P3 登记）：

```json
{
  "contracts": [
    {
      "id": "thread-items",
      "schema": "protocol/thread-items.schema.json",
      "consumers": ["src/lime_star/protocol/items.py"]
    }
  ]
}
```

语义：schema 文件变更后，清单里的每个消费者路径必须存在；且必须运行 `check-contracts.mjs --update` 显式确认"本轮同步已完成"。缺消费者或未确认都会让门禁失败。

## 扩展 verify-local 任务表

编辑 `verify-local.mjs` 顶部的 `TASKS`：`prefixes` 为空数组表示恒跑；否则是 POSIX 风格路径前缀。典型扩展：

```js
{ name: 'typecheck', prefixes: ['src/', 'tests/'], cmd: 'uv run mypy' },
{ name: 'test:unit', prefixes: ['src/', 'tests/'], cmd: 'uv run pytest -q' },
```

原则：**每条 AGENTS.md 硬规则都应有对应的机械守卫**，并挂进 verify-local 的任务表；没有守卫的规则只是建议，不是规则。
