# 治理规则：能力生命周期与守卫

边界、目录归属和依赖方向以 `architecture.md` 为准；本页定义同一种能力"新旧并存"时如何收敛，以及退役后如何防回流。

## 1. 四态生命周期

同一种能力在同一时期只能有一个继续演进的 owner。先写清事实源，再动代码：

- `current`：唯一产品路径，可以新增能力。
- `compat`：只做边界适配和委托，不得新增业务逻辑。
- `deprecated`：只允许迁出和删除，不得修复性扩展。
- `dead`：无入口或已被替代，物理删除并补回流守卫。

## 2. 直接替换原则

本项目没有外部用户和历史数据负担，因此直接替换是绝对规则：发现重复实现、临时路径或已脱离构建图的代码，优先删除或直接替换，不保留双轨；不要为了降低 diff 新增新的 compat 层。

## 3. 修改前四层盘点

改动前按四层盘点；若无法指出唯一 current owner，不扩展功能，先完成收敛：

1. 入口层：用户从哪里进入这个能力？（CLI 命令、app 回合入口）
2. 编排层：哪段循环或编排逻辑是事实源？
3. 存储层：数据落在哪里、谁拥有 schema？（transcript、请求日志）
4. 旁路层：是否有脚本、测试夹具、导出或环境开关绕过以上三层？

## 4. 退役三件套

把能力标记为 dead 时必须同时完成：

1. **物理删除**：删除实现、入口、fixture、文档入口；历史由 Git 承载，不保留注释掉的尸体。
2. **负向守卫**：在测试或守卫脚本中断言旧名、旧路径不得回流（依赖、命令、文案、文档四个面）。
3. **forbidden-to-restore 措辞**：在 architecture.md 第 4 节与执行计划收尾中写明 `<旧名>` 为 dead / deleted / forbidden-to-restore，覆盖到具体函数名、类型名、事件名级别。

原则：未知的能力、配置或开关值必须 fail closed，不能由名称、别名或默认值放行。

## 5. 守卫与验证命令

| 规则 | 守卫 |
| --- | --- |
| 行数棘轮 800/1000 | `node scripts/check-file-size-governance.mjs` |
| scripts 冻结基线 | `node scripts/check-scripts-baseline.mjs` |
| 契约同步 | `node scripts/check-contracts.mjs` |
| 文档交叉引用 | `node scripts/check-doc-links.mjs` |
| 依赖方向与禁止旁路（architecture.md 第 4 节的依赖矩阵，模型客户端 SDK 只在 model_provider） | verify-local 的 architecture 任务：`tests/integration/test_guard_architecture.py` |
| 重大架构变更的确认块（architecture.md 第 7 节的每个 Owner 章节） | verify-local 的 architecture 任务：`tests/integration/test_guard_architecture.py` |
| 第二份会话真相（显示、导出、测试只能从 thread_store 的会话记录派生） | Gate A 测试：`tests/integration/test_transcript.py` 里 read_thread 的结果与文件逐项一致的用例 |
| 审批硬规则（标记为危险的操作必须经 app 回合入口的 respond_action 批准后才能执行） | Gate B 冒烟：`scripts/smoke/agent_gate_b.py` 里对着会话记录的断言，每个危险调用都先有批准项、后有结果，被拒绝的没有执行 |
| 全部聚合 | `npm run verify:local` |
| 旧路径回流 / dead 残留 | 尚无退役对象。首次退役时在 architecture.md 第 4 节登记，并在该阶段的计划里补负向守卫 |

有违规即失败；基线只许收缩式更新，`--update` 是"确认现状"，不是赦免。

## 6. 清理工作去哪里

直接服务主链的删除随任务走；无法回挂路线图的清理登记到 `internal/exec-plans/tech-debt-tracker.md`，带编号、退出条件和负责人。tech-debt 条目不允许无退出条件地长期滞留。
