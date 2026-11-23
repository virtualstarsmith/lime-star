# internal/aiprompts — 工程事实源导航

本目录是领域规则事实源。分工：`architecture.md` 是全局架构唯一裁决源；本 README 只做场景路由，不定义规则；各领域文档只补充具体契约，不得建立第二套运行时或改写 architecture.md 的边界。

## 场景路由

| 我要做什么 | 先读 | 再看 |
| --- | --- | --- |
| 动手改代码前的全局认知 | architecture.md | 根 AGENTS.md |
| 判断某能力归谁管、能不能动 | governance.md | architecture.md 对应 owner 章节 |
| 评估一轮改动的验证范围 | quality-workflow.md | 对应执行计划 |
| 验证一条真实用户路径是否跑通 | `../develop/traceable-acceptance.md` | 当前阶段的执行计划 |
| 删除、替换、退役能力 | governance.md | `../exec-plans/tech-debt-tracker.md` |
| 与其他 Agent 并行开发 | parallel-agent-collaboration.md | 当前任务的执行计划 |
| 开始一个长任务或进入路线图下一阶段 | `../roadmap/README.md` | `../exec-plans/README.md` |
| 写需求，或判断一个功能做不做 | `../prd/README.md` | 对应的路线图阶段 |
| 调查对标产品，或查已有的研究结论 | `../research/README.md` | 研究里列出的来源路径 |
| 新增脚本或门禁 | `../../scripts/README.md` | governance.md |
| 第一次接触这套范式 | `../develop/paradigm-learning-guide.md` | 本页 |

## 文档清单

本目录只收录当前有效的规则；新增领域文档时在此登记一行，文档被替代时直接删除并同步本表。

| 文档 | 用途 |
| --- | --- |
| architecture.md | 全局架构唯一裁决源：裁决顺序、目录地图、主链、依赖方向、重大变更确认 |
| governance.md | 能力生命周期治理：四态、直接替换原则、退役三件套、守卫 |
| quality-workflow.md | 证据分级、改动类型到最低验证的矩阵、测试作者合同 |
| parallel-agent-collaboration.md | 多 Agent 并行协议：窄写集、热区避让、收尾五项汇报 |

本目录之外的相关事实源：

| 文档 | 用途 |
| --- | --- |
| `../develop/traceable-acceptance.md` | 可追踪验收方法论 |
| `../develop/paradigm-learning-guide.md` 与 `../develop/paradigm-quick-checklist.md` | 范式学习材料与日常速查 |
| `../prd/README.md` | 需求层：目标、范围与成功标准 |
| `../roadmap/README.md` | 路线图层：阶段目标、顺序与验收动作 |
| `../research/README.md` | 研究层：对标调查的结论、来源与核对日期 |
| `../tech/harness/README.md` | harness 反馈层的目标链 |
| `../test/harness-evals.md` | 评测任务集的目标形状 |

## 维护规则

1. 本目录只收录"当前有效"的规则；历史迁移日记和实现副本禁止放入。
2. 每个文件单一主题；接近 800 行优先拆分（受仓库行数棘轮约束）。
3. 文档间引用使用相对路径，保证整目录可迁移。
4. 领域文档开头必须声明与 architecture.md 的关系（"边界以 architecture.md 为准"），形成单向引用闭环。
