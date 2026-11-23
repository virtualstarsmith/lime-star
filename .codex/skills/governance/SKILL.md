---
name: governance
description: 在 lime-star 中收敛新旧并存的实现，判定 current、compat、deprecated、dead，执行退役三件套并用守卫封住回流。只问结论时先给短结论。
---

# 治理与立即替换

先读 `internal/aiprompts/governance.md`（事实源）。目录归属与依赖方向看 `internal/aiprompts/architecture.md`；需要快速找入口再看 `internal/aiprompts/README.md`。

## 快速路径

仓库所有者只问"能不能删""是否已经 dead""结论是什么"时，先用 3 到 8 行给出结论和关键证据，不要自动展开成全量盘点或长清单。只有对方要求继续收敛、补守卫或实现时，才进入完整工作流。

## 何时使用

- 同一种能力出现两份实现，或 compat 路径长期活着
- 需要删除、替换或退役一段代码
- 需要为旧路径补守卫

## 工作流

1. **先盘点，再修改。** 用 rg 找出同一能力在入口层、编排层、存储层、旁路层（脚本、测试夹具、文档）的分布。不要在盘点前"顺手统一"。
2. **定事实源并分类。** 写出一句事实源声明，把实际路径标成 current、compat、deprecated、dead 之一。说不出唯一 current owner 时，不扩展功能。
3. **优先做减法。** 把散落逻辑收回单一边界，删除零引用入口；不为降低 diff 新增 compat 层。
4. **退役三件套。** 物理删除；补负向守卫；在 architecture.md 第 4 节和执行计划里写 dead / deleted / forbidden-to-restore。
5. **跑最贴边界的验证。** 默认 `npm run verify:local`；触及 scripts 目录时确认冻结基线；触及契约时跑 `npm run test:contracts`。
6. **按根 AGENTS.md 执行方式第 4 条收尾。** 如果任务来自路线图，再加一行：这一刀与主目标的关系，以及下一步回到哪条主链。

## 约束

- 治理删除只在直接服务主线时进行；"仓库里还能继续清理"不是更高的优先级。
- 自动扫描给出的候选信号只是线索，不能替代 dead 结论。
- 不假设存在外部 reviewer、hook 或 CI 替你把关；标准以仓库内文档为准。
- 本轮无法彻底收口时，明确说明还差哪条旁路或哪个旧入口没迁完。
