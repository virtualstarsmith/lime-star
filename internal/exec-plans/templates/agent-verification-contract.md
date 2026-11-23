# Agent Verification Contract（验证合同）

<!-- 主链改动（业务主链、协议边界、持久化）在计划文件内填写本合同；普通改动不强制。 -->

预算标签: <!-- budget:tight（最小验证）/ budget:normal（定向+门禁）/ budget:release（全量+Gate B） -->

主链: <!-- 本改动落在业务主链的哪一段；涉及多段逐条列出 -->

Happy Path:

1. <!-- 用户/调用方的完整成功路径，按步骤写 -->

Evidence Layers:

- 必须达到: <!-- Gate B / Current fixture / ... 引用 aiprompts/quality-workflow.md 证据分级 -->
- 禁止替代: <!-- 例如"单测不得冒充 Gate B evidence" -->

必跑命令:

| 命令 | 目的 | 状态 |
| --- | --- | --- |
| `npm run verify:local` | 本地门禁 | 未跑 |
| <!-- TODO --> | <!-- TODO --> | 未跑 |

未跑命令必须写：未跑 / 原因 / 风险 / 后续触发条件。

失败回写: 测试失败时三选一——修产品、修测试、补守卫；在合同内记录选择了哪个。

完成标准:

- [ ] 必跑命令全部有结果记录
- [ ] 证据等级达到 Evidence Layers 要求
- [ ] 下一刀已写明
