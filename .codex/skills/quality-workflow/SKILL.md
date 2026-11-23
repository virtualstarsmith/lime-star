---
name: quality-workflow
description: 为 lime-star 的一轮改动选择与风险匹配的验证，区分证据等级，并按固定格式汇报。只读分析或纯文档改动使用轻量检查。
---

# 质量验证

先读 `internal/aiprompts/quality-workflow.md`（事实源），按其中的最低验证矩阵执行。公共边界、目录和依赖方向看 `internal/aiprompts/architecture.md`。

## 先确定这次要证明什么

- 只读分析、纯规则文档：检查格式、链接和相关文档守卫；没有产品代码变化时不跑全量测试。
- 实现任务先写清 current owner、输入、用户可见结果和失败终态。主链改动开始前填写 `internal/exec-plans/templates/agent-verification-contract.md`。

## 验证顺序

1. 先跑受影响的 pytest 定向测试。纯逻辑归单元测试；接线归从 app 回合入口进入的集成测试。
2. Python 改动跑 ruff 与 mypy（路线图 P0 起）。
3. 协议、schema、消费者变更补 `npm run test:contracts`，并用 `--update` 登记确认。
4. 回合循环、工具、审批、恢复等主链改动：先 Current fixture，再 Gate B 冒烟（路线图 P4 起）。
5. 默认本地门禁 `npm run verify:local`。

扩大测试必须由新改动、失败或未关闭的风险支持；已有通过结果不因收尾而重复运行。

## 证据与汇报

- Unit、Domain integration、入口集成、Current fixture、Gate A、Gate B、Live 分别报告，不能互相替代。
- 回放夹具跑出的结果要标注模型来源，不冒充真实模型。
- 汇报包含：风险类型、改动分类、实际命令及结果、证据等级、未跑原因、剩余阻塞、来源声明。
