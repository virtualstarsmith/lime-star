# 全局架构（唯一裁决源）

本文件是全局架构的唯一裁决源。领域文档只能补充具体契约，不能建立第二套运行时或改写这里的边界。

> 状态：目标布局。目录地图中标"路线图 P<N>"的条目随 internal/roadmap/agent-practice.md 的对应阶段落地；落地前不得提前创建，也不得在未登记的目录写代码。
> 参考来源：lime 仓库 internal/aiprompts/architecture.md 的裁决顺序与 owner 划分方式，按本项目语境改写。
> lime 仓库在本机的位置：D:\aiproject\aiproject\lime，仅用于对照阅读。

## 1. 裁决顺序

冲突时按以下顺序裁决：

1. 当前构建图、协议 schema、运行代码和稳定测试
2. 本架构图与根 AGENTS.md
3. `internal/aiprompts/` 领域边界
4. `internal/exec-plans/` 执行计划
5. 路线图、需求、研究和 Git history

## 2. 仓库目录地图

每个目录必须写清 owner 与禁止放入内容；没有 owner 的目录不准收代码。

| 目录或文件 | 归属 owner | 职责 | 禁止放入 | 状态 |
| --- | --- | --- | --- | --- |
| `src/lime_star/cli/` | Surface | 终端入口、参数解析、终端投影、向用户发起审批 | 业务编排、provider 请求拼装、绕过 app 直接调用循环或工具 | 路线图 P0 |
| `src/lime_star/app/` | 回合入口（唯一边界） | start_turn、read_thread、respond_action | 第二套执行链 | 路线图 P1 |
| `src/lime_star/model_provider/` | 模型边界 | 模型配置、OpenAI 兼容请求、流式解析、请求日志 | 回合循环、工具权限、持久化 | 路线图 P1 |
| `src/lime_star/protocol/` | 协议类型 | Thread、Turn、Item 的类型与事件形状 | 运行时逻辑、I/O | 路线图 P2 |
| `src/lime_star/agent_runtime/` | 回合循环 | 循环状态机与回合编排 | provider wire 细节、工具执行、终端输出 | 路线图 P2 |
| `src/lime_star/tool_runtime/` | 工具边界 | 工具注册、参数校验、路径边界、危险等级、执行 | 终端交互、provider 请求 | 路线图 P2 |
| `src/lime_star/thread_store/` | 持久化 | transcript 追加写入、读取与读模型 | 临时界面状态、第二份会话真相 | 路线图 P3 |
| `protocol/` | 契约 schema | Thread、Turn、Item 的 JSON Schema | 实现代码 | 路线图 P3 |
| `tests/` | 测试 | unit、integration、fixtures | 生产代码、真实凭证 | 路线图 P0 |
| `pyproject.toml`、`uv.lock`、`.python-version` | 依赖与工具链 | 依赖声明与锁定、检查工具配置 | 业务逻辑 | 路线图 P0 |
| `.lime-star/` | 运行时产物 | transcript、请求日志、证据导出；不入库 | 需要长期保留的样本（应提升到 tests/fixtures/） | 路线图 P1 |
| `package.json` | 治理命令 | 只承载门禁命令 | 产品依赖 | 已有 |
| `scripts/` | 工具链 | 治理脚本；冒烟与 harness 脚本随路线图加入 | 业务逻辑 | 已有 |
| `governance/` | 治理基线 | 基线 JSON 与契约清单 | 临时文件 | 已有 |
| `.github/` | CI 工作流 | 复跑本地门禁：`node scripts/verify-local.mjs --full` | 业务逻辑；不经 verify-local 的第二套检查 | 已有 |
| `internal/aiprompts/` | 工程事实源 | 架构、治理、质量、目录准入、并行协作 | 历史迁移日记和实现副本 | 已有 |
| `internal/develop/` | 方法论 | 范式学习材料与可追踪验收方法论 | 项目进度 | 已有 |
| `internal/exec-plans/` | 执行进度 | 计划、阻塞、技术债 | 路线图、需求、研究等长期文档 | 已有 |
| `internal/prd/` | 需求 | 以用户目标写清做什么、不做什么、怎样算满足 | 实现步骤、排期、研究过程 | 已有 |
| `internal/roadmap/` | 路线图 | 按阶段写方向、顺序与验收动作 | 逐刀的写集与验证细节、实现细节 | 已有 |
| `internal/research/` | 研究 | 对标调查的结论、来源与核对日期 | 复制来的外部原文、未经核实的转述 | 已有 |
| `internal/tech/`、`internal/test/` | 设计目标 | harness 反馈层的目标链、评测任务集的目标形状 | 实现代码 | 已有 |
| `.codex/skills/` | 工作流入口 | 高频流程的路由与执行判断 | 规则正文（规则在 internal/aiprompts/） | 已有 |

## 3. 业务主链

```text
CLI 输入
  -> app 回合入口
  -> agent_runtime 回合循环
  -> model_provider / tool_runtime
  -> thread_store 的 Thread/Turn/Item transcript
  -> CLI 投影 / evidence 导出
```

这条主链的固定判断：

1. **app 回合入口是唯一提交点。** CLI、测试和将来的其他入口都从这里提交回合、读取线程、回应审批，不直接调用循环、模型或工具。
2. **循环是纯核心。** 回合循环的状态机不联网，不依赖具体模型客户端、工具实现或存储实现。
3. **一步一物化。** 每次模型响应先落成 item（文本、推理、工具调用）；一次响应里的工具全部执行完、结果写回同一份 transcript 之后，才进行下一次模型请求。
4. **transcript 是唯一事实源。** 终端显示、证据导出、回放和评测都只能从它派生。
5. **证据与回放是下游。** 它们只消费 transcript，不得反向定义运行时真相。

## 4. 依赖方向与禁止边界

- 依赖只能单向：cli -> app -> agent_runtime -> model_provider、tool_runtime、thread_store。
- protocol 被各层引用，自身不依赖任何层。
- 禁止反向依赖与跨层旁路：cli 绕过 app；agent_runtime 依赖 cli；model_provider 依赖 tool_runtime；脚本或测试夹具之外的第二条执行链。
- 已退役名单：暂无。首次退役时在此登记，格式为"<名称>为 dead / deleted / forbidden-to-restore"，精确到函数名、类型名或事件名。

## 5. 重大架构变更与开发者确认

满足以下任一条件即为重大架构变更：新增/删除顶层目录或 owner；改变业务主链；改变协议边界；引入新的持久化或 transport；复活任何 dead 条目。

重大变更必须在同一变更集中更新本文件对应章节，并在执行计划与 PR 描述中粘贴确认块：

```text
Architecture impact: major
架构图已更新：<章节号与链接>
Responsible developer confirmation: <姓名/代号>, <日期>
确认内容：<一段话说明改动、替代方案与回滚策略>
```

未确认的重大变更不得标记完成，不得进入 release evidence。

## 6. 实施前检查

动手前逐条确认：

- [ ] 能指出本次改动涉及能力的唯一 current owner；
- [ ] 已读对应领域文档与最近相关执行计划；
- [ ] 改动范围与执行计划的写集一致；
- [ ] 验证方式已按 quality-workflow.md 的矩阵确定；
- [ ] 若为重大变更：本文件的更新与确认块已准备。

## 7. Owner 章节（滚动追加）

每个跨层能力在本节之后各占一章，记录：主链、owner、边界、相关协议与退出条件。章节顺序编号；重大决策随章节落确认块。退役能力删除章节并在第 4 节登记负向守卫。

暂无。路线图 P2 起逐阶段追加。
