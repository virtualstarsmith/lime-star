# 日常速查检查单

配合 `paradigm-learning-guide.md` 使用。每张检查单对应一个时刻，逐条打勾。

## 1. 开工检查单

- [ ] 判断任务规模：长任务（多轮/跨会话/影响主链）→ 建 `internal/exec-plans/<topic>-plan.md`
- [ ] 计划写了：目标（不是实现步骤）、当前事实、写集与避让、阶段与退出条件
- [ ] 主链改动 → 填验证合同（`internal/exec-plans/templates/agent-verification-contract.md`）
- [ ] 并行场景（有其他 Agent / 工作树有无关脏改动）→ 只读盘点 `git status --short -- <scope>`，声明三段写集（认领/只读/不碰）
- [ ] 动手前已读：AGENTS.md → 相关领域文档 → 相关执行计划
- [ ] 能指出本次改动涉及能力的唯一 current owner（答不出 → 先收敛，参考 governance.md 四层盘点）

## 2. 每刀收口检查单

- [ ] 改动范围 ⊆ 计划写集；越界先改计划再改代码
- [ ] 按最低验证矩阵跑命令（见第 5 张检查单）
- [ ] 计划"进度记录"追加一刀：改动 / 验证（命令+结果+证据等级）/ 完成度 % / 下一刀
- [ ] 未跑的命令写了：未跑 / 原因 / 风险 / 后续触发条件
- [ ] 没有用低级证据冒充高级证据（单测 ≠ Gate B）
- [ ] 测试失败走了"回写"三选一：修产品 / 修测试 / 补守卫
- [ ] 冲突或意外变化：停、上报、没有 checkout/reset 抹平

## 3. 收尾检查单

- [ ] 计划"当前结论"写了治理四分类：current / compat / deprecated / dead 增删
- [ ] 验证结果与未验证原因写全
- [ ] 完成度百分比（未验证部分不计入完成）
- [ ] 被替代的旧实现走了退役三件套：物理删除 + 负向守卫 + forbidden-to-restore 措辞
- [ ] 需要挂账的清理进了 `internal/exec-plans/tech-debt-tracker.md`（带退出条件）
- [ ] 重大架构变更：architecture.md 已在同一变更集更新 + 确认块已填
- [ ] 删除集兑现：入口、fixture、文档入口都清了，历史归 Git

## 4. 并行协作检查单

- [ ] 协议触发条件成立才启用；单 Agent 时不空转协议
- [ ] 只读盘点在先，没有先改文件
- [ ] 写集三段式且足够窄（垂直切片，不是"整个 src/xxx"）
- [ ] 目标文件已脏 → 不夹写，切只读审阅
- [ ] 必须同改 → 先汇报补丁点（文件+行区间+意图），等合并窗口
- [ ] 共享热区（清单见 `internal/aiprompts/parallel-agent-collaboration.md` 第 3 节）先登记再动手
- [ ] 主计划有并行分歧 → 不夹写主计划，改写独立 `<topic>-progress.md`
- [ ] 收尾五项汇报：认领写集 / 避让写集 / 验证口径 / 下一刀归属 / 治理分类

## 5. 门禁速查（改动类型 → 最低验证）

| 改动类型 | 必跑 | 说明 |
| --- | --- | --- |
| 任何改动 | `npm run verify:local` | 默认门禁，增量选任务 |
| 协议 / schema / 契约 | `npm run test:contracts` | 同步消费者后 `check-contracts.mjs --update` 确认 |
| 业务主链 | Current fixture + Gate B 冒烟 | Gate A 不能替代 Gate B |
| 新增脚本 | 放进 `scripts/<domain>/` 或 `scripts/lib/` | scripts 冻结基线，根目录新文件即违规 |
| 大文件 | `scripts/check-file-size-governance.mjs` | 800 预警 / 1000 硬限，基线只许收缩 |
| 退役能力 | 负向守卫 | dead / deleted / forbidden-to-restore |
| 架构变更 | 确认块 + 架构图更新 | 未确认不得标记完成 |
