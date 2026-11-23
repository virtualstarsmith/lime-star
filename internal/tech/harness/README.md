# Harness 反馈层

> 状态：设计目标，未接入。脚本与入口随路线图 P6 落地；落地之前不得宣称已有 evidence、replay 或评测能力。
> 参考来源：lime 仓库 internal/tech/harness/README.md 与 internal/aiprompts/harness-engine-governance.md 的导出链思想，按 lime-star 语境改写。

## 目标链

```text
runtime transcript
  -> evidence 导出
  -> replay case
  -> 评审与评测
  -> 趋势与人读的摘要
```

运行时事实的唯一 owner 是 thread_store 里的 transcript。回放、评审、评测和摘要都是派生物，只能单向消费它。

## 固定约束

- **先导出事实，再导出判断。** 证据包先落关联键、时间线、工具与命令结果、警告和真实发生过的验证记录；解释性内容只能建立在它之上。
- **只导出适用的信号。** 本轮没有发生的验证不导出，不用空数组占位。
- **展示层不是事实源。** 摘要、文案与证据包冲突时，以 transcript 和证据包为准。
- **派生层不回读重拼。** replay 复用证据包，评测复用 replay；不允许每一层各自重读 transcript 拼出另一份摘要。

## 与路线图的关系

P3 建立 transcript 事实源，P6 落地本层脚本。在 P6 之前，本页只用来指导 P3 的数据形状设计：记录要带关联键，要能被导出。
