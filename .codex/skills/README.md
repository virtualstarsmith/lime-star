# lime-star 仓库技能索引

本目录存放 lime-star 的项目级 skills。skill 不替代根 `AGENTS.md` 或 `internal/aiprompts/` 的事实源，只把高频工作流做成可重复执行的入口：只做路由和执行判断，规则正文一律引用事实源。

## 当前仓库级 skills

| skill | 何时使用 | 事实源 | 状态 |
| --- | --- | --- | --- |
| `governance` | 新旧实现并存、要收敛或退役能力、判断能否删除 | `internal/aiprompts/governance.md` | 启用 |
| `quality-workflow` | 为一轮改动选择验证、判断证据等级、按固定格式汇报 | `internal/aiprompts/quality-workflow.md` | 启用 |
| `acceptance-loop` | 验证一条真实用户路径是否跑通，并给出分级结论 | `internal/develop/traceable-acceptance.md` | 启用 |
| `skill-factory` | 把重复出现的工作流提炼成新 skill | 本索引 | 启用 |
| `release` | 准备并执行一次发版 | `internal/aiprompts/quality-workflow.md` | 骨架，路线图 P7 启用 |

## 入口关系

- 仓库规则：看根 `AGENTS.md`
- 文档索引：看 `internal/aiprompts/README.md`
- 模块与流程事实源：看 `internal/aiprompts/` 和 `internal/develop/` 下的文档
- 高频工作流执行入口：看本目录下的各个 skill

## 维护规则

1. 同一流程重复出现两三次、且每次都要重新解释长规则，才提炼成 skill；做法见 `skill-factory`。
2. 新增或重构 skill 时，同步检查它引用的事实源是否仍然存在、是否仍是唯一来源。
3. skill 只写影响决策的本仓库特有约束；假设 Agent 已会通用编程。
4. 新 skill 使用短的领域词命名，`name` 与目录名一致。
