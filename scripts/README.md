# scripts/ — 治理脚本目录

本目录是**冻结基线目录**：根目录文件与一级领域子目录由 `governance/scripts-baseline.json` 冻结，新增脚本必须进入既有领域子目录，不允许散落在根目录。此规则由 `check-scripts-baseline.mjs` 机械执行。

这些脚本只做治理检查，不写业务逻辑。产品代码是 Python。

## 脚本清单

| 脚本 | 作用 | 用法 |
| --- | --- | --- |
| `verify-local.mjs` | 默认本地门禁编排器：按改动路径增量选任务，fail-fast | `node scripts/verify-local.mjs [--full] [--dry-run] [--only a,b]` |
| `check-file-size-governance.mjs` | 行数棘轮：新文件超过 800 行违规，超过 1000 行硬违规；基线文件只许收缩 | `node scripts/check-file-size-governance.mjs [--root <dir>] [--update]` |
| `check-scripts-baseline.mjs` | scripts 目录冻结基线与垃圾产物检查 | `node scripts/check-scripts-baseline.mjs [--root <dir>] [--update]` |
| `check-contracts.mjs` | 契约同步门禁：schema 变更必须同步消费者并显式确认 | `node scripts/check-contracts.mjs [--root <dir>] [--update]` |
| `check-doc-links.mjs` | 文档交叉引用守卫：规则、计划、手册之间的相对引用不许断链；带目录的引用必须按路径在仓库内找到，只有裸文件名可按文件名全树查找 | `node scripts/check-doc-links.mjs [--root <dir>]` |
| `scripts/security/check-secrets.mjs` | 密钥守卫：`.env` 必须被 Git 忽略且不被跟踪；已跟踪文件里不得出现常见格式的密钥。报出位置和规则名，不回显密钥 | `node scripts/security/check-secrets.mjs [--root <dir>]` |

所有脚本零依赖（Node 18 或更高），必须在**仓库根目录**运行，违规时退出码非 0。

## 接入状态

lime-star 已于 2026-11-23 完成接入，记录见 `internal/exec-plans/paradigm-port-plan.md`。当前基线：根文件 6 个（5 个脚本加 README），一级目录 1 个（security，路线图 P1 建立，记录见 `internal/exec-plans/p1-chat-plan.md`）。

三个基线文件都在 `governance/` 下，属于**必须提交**的版本化文件：

- `governance/scripts-baseline.json`：scripts 目录结构快照。结构变化后需要 `--update`，并在计划中说明理由。
- `governance/file-size-baseline.json`：超过 800 行文件的行数棘轮；只在拆分完成或明确登记退出条件时收缩式更新。
- `governance/contracts.json`：契约清单，人工维护。`governance/contracts-state.json`：schema 哈希，由 `--update` 生成。

## 路线图新增的目录

路线图分阶段新增三个一级目录：security（P1，密钥守卫，已建立）、smoke（P4，Gate B 冒烟）、harness（P6，证据导出与评测）。每次新增都必须在该阶段的执行计划里写明理由，再运行 `node scripts/check-scripts-baseline.mjs --update`。

## 守卫脚本的回归用例

治理脚本自己也要有仓库内的回归。用例放在 `tests/integration/` 下，文件名以 `test_guard_` 开头：在临时目录里运行真实的脚本进程，断言退出码和输出。verify-local 的任务 test:guards 在 scripts/ 或这些用例变动时执行它们。

## 重新生成基线

```bash
node scripts/check-scripts-baseline.mjs --update
node scripts/check-file-size-governance.mjs --update
node scripts/verify-local.mjs --dry-run
```

## 契约清单格式

`governance/contracts.json` 的格式示例（lime-star 的第一条真实契约由路线图 P3 登记）：

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
