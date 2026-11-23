# lime 开发范式对照

> 核对日期：2026-11-23。只读快照，lime 仓库此后可能已变化。
> 本页是研究结论，不是规则；落地记录见 `../exec-plans/paradigm-port-plan.md`。
> 参考的 lime 路径（只读，未复制原文；lime 仓库的位置见 `../aiprompts/architecture.md`）：AGENTS.md；internal/README.md；internal/aiprompts 下的 architecture.md、governance.md、quality-workflow.md、README.md、parallel-agent-collaboration.md、project-heatmap.md、harness-engine-governance.md；internal/exec-plans/README.md 与 tech-debt-tracker.md；internal/develop、internal/test、internal/tests 的文件清单；internal 其余一级目录的文件清单；package.json 的 scripts；scripts 的文件清单；.github/workflows 下的 quality.yml 与 harness-nightly.yml；.husky/pre-commit；.codex/skills/README.md。

## 问题

lime-star 搬入的是 lime 的开发范式。两者相比，范式上差在哪里，哪些差距值得补。

## 方法

只读盘点两个仓库的对应目录，逐层比较文件数量、机制有无和导航引用。

## 结论

### 1. 骨架一致

根 AGENTS.md 的结构、事实源分层、四态治理与直接替换、证据分级与测试作者合同、执行计划与验证合同模板、行数棘轮、脚本冻结基线、并行协议，lime-star 都有同源版本。范式级的五个技能一一对应。

### 2. lime 有、lime-star 的路线图没有安排的机制

| 机制 | lime 的做法 | lime-star 现状 |
| --- | --- | --- |
| 架构确认守卫 | 守卫脚本，加 PR 上的 CI 作业 | 只有规则和确认块格式 |
| 依赖方向守卫 | 导入边界守卫，加基线文件 | 只有规则 |
| 守卫脚本的测试 | scripts 下有 262 个测试文件 | 没有 |
| 机器化验收（qcloop） | 场景清单、证据 schema；worker 交证据，verifier 逐项核对 | 方法论和 markdown 模板 |
| 测试分层与预算 | 按文件后缀分层，预算守卫限制测试数量 | 证据分级和作者合同 |
| 依赖审计 | CI 跑依赖审计 | 只计划了锁文件检查 |

### 3. 体量差距

| 项目 | lime | lime-star |
| --- | --- | --- |
| internal/aiprompts | 41 个文件；architecture.md 6993 行，约 50 个 owner 章节 | 4 份文档加索引；architecture.md 101 行 |
| scripts | 890 个文件 | 5 个脚本加说明 |
| CI 工作流 | 8 个 | 1 个 |

体量来自产品成熟度，不是范式差距。

### 4. internal 的一级目录

lime 有 14 个一级子目录，lime-star 原有 5 个。多出来的 9 个处理如下。

| lime 的目录 | 内容 | 规模 | 处理 |
| --- | --- | --- | --- |
| roadmap | 36 个领域目录的路线图 | 224 个文件 | 已建；路线图文件移入 |
| prd | 需求文档 | 20 个文件 | 已建；放入需求草稿 |
| research | 对标研究 | 299 个文件 | 已建；放入本页 |
| test、tests、testing | 测试策略、场景清单、qcloop 手册 | 32、11、1 个文件 | 未建；测试规则仍在 quality-workflow.md |
| refactor | 重构方案与迁移台账 | 44 个文件 | 未建；没有存量代码 |
| design、knowledge、gongzonghao | 界面设计稿、功能说明、私有内容材料 | 各 1 个文件 | 未建；与范式无关 |

tech 两边都有：lime 6 个文件，lime-star 1 个。

### 5. lime-star 多出来的

收尾报告里的来源声明、语言分工与 Windows 验收环境、文档链接检查、通用契约清单、任务计划模板、路线图每个阶段固定七项、冷启动验收。

## 启示

- 已决定（2026-11-23，仓库所有者）：建立 prd、roadmap、research 三层。
- 候选，未排期：架构确认守卫、依赖方向守卫、守卫脚本的测试。三者成本低，直接对应 lime-star "每条规则配一个守卫"的原则。
- 候选，未排期：qcloop 与测试分层。等路线图 P6 的 harness 落地时再评估。
- 目录数量不是目标。lime-star 每加一层都要有唯一职责和明确边界。
