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
| `src/lime_star/cli/` | Surface | 终端入口、参数解析、终端投影、向用户发起审批 | 业务编排、provider 请求拼装、绕过 app 直接调用循环或工具 | 已有 |
| `src/lime_star/app/` | 回合入口（唯一边界） | start_turn、read_thread、respond_action | 第二套执行链 | 已有 |
| `src/lime_star/model_provider/` | 模型边界 | 模型配置、OpenAI 兼容请求、流式解析、请求日志 | 回合循环、工具权限、持久化 | 已有 |
| `src/lime_star/protocol/` | 协议类型 | Thread、Turn、Item 的类型与事件形状 | 运行时逻辑、I/O | 已有 |
| `src/lime_star/agent_runtime/` | 回合循环 | 循环状态机与回合编排 | provider wire 细节、工具执行、终端输出 | 已有 |
| `src/lime_star/tool_runtime/` | 工具边界 | 工具注册、参数校验、路径边界、危险等级、执行 | 终端交互、provider 请求 | 已有 |
| `src/lime_star/thread_store/` | 持久化 | transcript 追加写入、读取与读模型 | 临时界面状态、第二份会话真相 | 已有 |
| `protocol/` | 契约 schema | Thread、Turn、Item 的 JSON Schema | 实现代码 | 已有 |
| `tests/` | 测试 | unit、integration、fixtures | 生产代码、真实凭证 | 已有 |
| `pyproject.toml`、`uv.lock`、`.python-version` | 依赖与工具链 | 依赖声明与锁定、检查工具配置 | 业务逻辑 | 已有 |
| `.lime-star/` | 运行时产物 | transcript、请求日志、证据导出；不入库 | 需要长期保留的样本（应提升到 tests/fixtures/） | 已有 |
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
6. **危险操作先批准后执行。** write_file 与 run_command 只有在 app 回合入口经 `respond_action` 收到批准之后才执行；批准与拒绝都先写进会话记录。CLI 只负责提问和交回决定。

## 4. 依赖方向与禁止边界

- 依赖只能单向：cli -> app；app 是装配点，把循环、模型、工具、存储接在一起；agent_runtime、model_provider、tool_runtime、thread_store 各自只依赖 protocol。
- protocol 被各层引用，自身不依赖任何层。
- 禁止反向依赖与跨层旁路：cli 绕过 app；agent_runtime 依赖 cli；model_provider 依赖 tool_runtime；脚本或测试夹具之外的第二条执行链。
- 方向落成下面这张表。守卫按它检查 `src/lime_star/` 下每个包的导入，这张表是唯一来源；新增包先在这里登记一行，再写代码。根包 `lime_star` 只有版本号，任何包都可以导入它。

| 包 | 允许导入的本项目包 |
| --- | --- |
| `cli` | `app`、`protocol` |
| `app` | `agent_runtime`、`model_provider`、`tool_runtime`、`thread_store`、`protocol` |
| `agent_runtime` | `protocol` |
| `model_provider` | `protocol` |
| `tool_runtime` | `protocol` |
| `thread_store` | `protocol` |
| `protocol` | 无 |

- 模型客户端 SDK（openai）只允许出现在 model_provider。第二条执行链没法用导入检查发现，靠评审和根 AGENTS.md 里"新的入口只能接入 app 回合入口"的规则。
- 守卫是 `tests/integration/test_guard_architecture.py`：verify-local 的 architecture 任务在产品代码、本文件或守卫自身变动时执行它。
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

### 7.1 回合循环

落地于路线图 P2（2026-11-24）。阶段计划见 `../exec-plans/p2-loop-core-plan.md`。

- 主链：app 回合入口 `start_turn` -> agent_runtime 的 `run_turn` -> model_provider 的一次模型请求、tool_runtime 的一次工具执行 -> 每一步的结果按发生顺序写回会话记录 -> CLI 投影。P2 的会话记录是 app 内存里的项，P3 起由 thread_store 持有。
- owner：`src/lime_star/agent_runtime/` 是回合循环的唯一 current owner；`src/lime_star/protocol/` 是项、回合结局和三个边界接口的 owner；`src/lime_star/tool_runtime/` 是工具注册表的 owner。工具的完整边界（路径边界、危险等级、审批）见 7.3。
- 边界：
  1. 循环只依赖 protocol，不导入模型客户端、工具实现或存储。守卫是 `tests/integration/test_guard_architecture.py` 里的依赖矩阵检查。
  2. 循环通过三个接口与外界往来：模型（respond）、工具集（specs、execute）、会话记录（append）。接口是 protocol 里的结构化类型，由 app 在回合入口装配。
  3. 一步一物化：一次模型响应先落成项（推理、文本、工具调用）并写进记录，再执行其中的工具调用；一次响应里的工具全部执行完、结果都写回之后，才发起下一次请求。
  4. 一个回合最多 20 次模型请求（需求决策 D-10）。第 20 次响应仍调用工具时，一个工具也不执行，回合以步数上限结束。
  5. 模型请求失败结束回合，不重试；工具出错、未知工具、参数不合法都作为工具结果交回模型，回合继续。
  6. 正式命令的工具集由 tool_runtime 的 default_tools 给出，测试可以经 `open_session` 的 `tools` 参数换上自己的工具集。P2 时它是空的，请求与 P1 相同；P3 起含 read_file，见 7.2。
- 相关协议：项（UserMessage、ModelText、Reasoning、ToolCall、ToolResult）、Outcome（done、error、cancelled、step_limit）、ModelResult（ModelReply 或 ModelFailure）。项的 JSON Schema 契约随 P3 登记。
- 退出条件：回合循环被另一个 owner 取代时，删除 `src/lime_star/agent_runtime/`，在第 4 节登记 `run_turn` 为 dead / deleted / forbidden-to-restore，并把依赖矩阵里的这一行删掉。

```text
Architecture impact: major
架构图已更新：architecture.md 第 2 节目录地图（protocol、agent_runtime、tool_runtime 三行的状态列）、第 4 节的依赖矩阵、本节 7.1
Responsible developer confirmation: 仓库所有者，2026-11-24
确认内容：本阶段新增 protocol、agent_runtime、tool_runtime 三个 owner，回合入口第一次把回合交给循环，模型请求第一次能带上工具定义并取回工具调用。循环是只依赖 protocol 的纯核心，外界只经模型、工具集、会话记录三个接口进来。正式命令在这一阶段不向模型提供工具，可见行为与 P1 相同。替代方案：让循环直接依赖模型边界和注册表，被第 4 节的依赖方向禁止，守卫会拦；现在就把 read_file 挂到正式命令上，显示、会话记录和路径边界都还没有交付。回滚策略：删除三个新目录，Session.start_turn 回到只发一次请求，Provider 回到只取出回复文本；会话记录一直在内存里，磁盘上没有需要回滚的东西。
```

### 7.2 会话记录事实源

落地于路线图 P3（2026-11-24）。阶段计划见 `../exec-plans/p3-transcript-plan.md`。

- 主链：app 回合入口 `start_turn` -> agent_runtime 的循环 -> thread_store 把每一项追加进会话记录并落盘 -> 终端显示与 read_thread 只从这份记录派生。
- owner：`src/lime_star/thread_store/` 是会话记录（transcript）的唯一 current owner；仓库根的 `protocol/` 是会话记录一行这个契约的 owner，第一条契约是 thread-items。
- 边界：
  1. 一个会话只有一份记录：工作目录下 .lime-star/threads/<thread_id>.jsonl，JSON Lines，只追加（决策 D-23、D-29）。不在内存里保留第二份：app 在每个回合开始时从文件读出历史。
  2. 每一行是带信封的一项：序号、时间、会话标识、回合标识，加上项的类型和载荷。八类项见契约 thread-items；改类型、改编码、改 schema 三者要一起改，并重新登记契约。
  3. 每项写入后 flush 并 fsync，然后才继续处理。读回时，末尾没有换行的残行不算一项；看不懂的行直接报错，不悄悄丢掉。
  4. 循环经 protocol 里的 Journal 接口写记录。循环不导入 thread_store；app 负责把接口接上，并在每一项落盘后把它交给显示回调。
  5. 终端显示是记录的投影：`src/lime_star/cli/chat.py` 的 project 只看传进来的项，不留状态。回合怎样收场（完成、取消、步数上限、出错）也由回合结局项驱动显示。
  6. 记录里每次工具调用都有且只有一条结果。没有执行的调用由循环补一条出错的结果：取消时被中断的调用和它后面的调用，达到步数上限时最后一次响应里的调用。
  7. 模型可见的历史由会话记录的项转换而来，转换只在 model_provider 的 _messages 一处。回合结局项目前不上线路。
  8. 请求日志凭 thread_id 和 turn_id 与会话记录关联（R3.4）。两个标识由 app 在打开会话时生成，两边共用。
- 相关协议：契约 thread-items，schema 是 `protocol/thread-items.schema.json`，消费者是 protocol 的项类型、thread_store 的编码和契约用例。录制的模型响应放在 tests/fixtures/provider/ 下，只供测试回放；产品代码没有回放开关（R11.6）。
- 退出条件：会话记录能力被另一个 owner 取代时，删除 `src/lime_star/thread_store/`，在第 4 节登记 Transcript、encode、decode 为 dead / deleted / forbidden-to-restore，把依赖矩阵里的这一行删掉，并移除契约 thread-items。

```text
Architecture impact: major
架构图已更新：architecture.md 第 2 节目录地图（thread_store、protocol 两行的状态列）、本节 7.2
Responsible developer confirmation: 仓库所有者，2026-11-25
确认内容：本阶段新增 thread_store 和契约目录两个 owner，第一次把会话记录持久化到磁盘，并让终端显示只从它派生。正式命令第一次向模型提供工具：read_file，带工作目录边界。替代方案：让显示直接吃循环发出的事件而不落盘，那样显示会成为第二份会话真相，回放和证据也无从派生；把回放做成产品命令的开关，被 R11.6 禁止，所以回放只经测试注入的 HTTP 传输。回滚策略：删除 thread_store 和仓库根的 protocol 目录，取消契约登记；Session 回到 P2 的内存记录，cli 回到按回合结局显示；默认工具集回到空。已经在工作目录 .lime-star/threads 下写出的记录文件不需要迁移，回滚后没有代码读它们。
```

### 7.3 工具与审批

落地于路线图 P4（2026-11-26）。阶段计划见 `../exec-plans/p4-tools-approval-plan.md`。

- 主链：app 回合入口 `start_turn` -> agent_runtime 的循环 -> tool_runtime 的一次工具执行。执行危险操作之前，工具边界向 app 请求批准；app 经提问回调请 CLI 向用户提问，CLI 用 `respond_action` 交回决定；app 把批准项写进会话记录之后才放行 -> CLI 投影。
- owner：`src/lime_star/tool_runtime/` 是四个工具、工作目录边界、危险等级和执行前批准的唯一 current owner。app 回合入口是批准流程和 `respond_action` 的 owner。CLI 只负责向用户提问并把决定交回 app。
- 边界：
  1. 危险与否按工具固定（决策 D-19）：write_file 和 run_command 是危险操作，read_file 和 list_dir 不是。危险工具带一个 danger，注册表在调用它的执行函数之前一定先经批准来源取得批准；拿不到就不执行，给出"用户拒绝了这次操作"的结果。这是结构性的保证，不靠每个工具自觉（R7.6、R7.10、R7.13）。
  2. 批准来源由 app 在每个回合绑定（`Registry.approved_by`）。决定做出之后、操作执行之前，app 先把批准项写进会话记录（R7.12），所以记录里的顺序固定是：工具调用、批准、工具结果。等待中的批准只在内存里：进程在等待时被结束，记录里没有批准项，操作也没有执行（R9.3-S2）。
  3. 路径边界只约束文件工具（read_file、list_dir、write_file），按真实位置判断；越界的调用不进入批准提示（R8.2-S2）。run_command 不做路径检查，唯一的安全边界是审批（R8.4，决策 D-22），批准提示显示原样的命令（R7.8）。
  4. 注定失败的调用（越界、父目录不存在、目标是个目录、参数不合法）不进入批准提示，直接作为工具结果交回模型。
  5. CLI 只在提示出现之后才接受回应：提示之前到达的输入按回合中的输入丢弃（R13.8）；只有 y 算批准（R7.9，决策 D-20）。提问回调可以先返回、稍后再交回决定，所以别的界面也能接同一个入口。
  6. 命令的进程被圈在一棵进程树里：Windows 上是作业对象，其他平台是进程组。超时（R7.4）和 Ctrl+C（R12.5-S1）都是结束整棵树。命令执行到一半被打断时，已经产生的输出作为这次调用的结果如实记下（protocol 的 Halted），不说成"没有执行"。
  7. 终端摘要按决策 D-08 只占一行：命令输出不回显到终端，它在会话记录里。
- 相关协议：Approval（决定）、Pending（等待批准的操作）、Approver（批准来源）、Halted（被中断的工具带回的结果），都在 protocol。会话记录一行的形状没有变。
- 守卫：Gate B 冒烟 `scripts/smoke/agent_gate_b.py` 对着会话记录断言每个危险调用都先有批准项、后有结果。入口集成、真实进程、真实控制台三层用例在 tests/integration。
- 退出条件：这套能力被另一个 owner 取代时，删除对应的工具和 `respond_action`，在第 4 节登记 `Registry.approved_by`、`Session.respond_action` 为 dead / deleted / forbidden-to-restore，删除本章和根 AGENTS.md 的审批硬规则。

```text
Architecture impact: major
架构图已更新：architecture.md 第 3 节加一条固定判断、本节 7.3；7.1 的指引改指 7.3
Responsible developer confirmation: 仓库所有者，2026-11-26
确认内容：本阶段不新增目录，也不改依赖矩阵：tool_runtime、app、cli 三个 owner 都已存在。改变的是业务主链：危险操作在执行之前多了一个节点，批准；回应它经 app 回合入口的 respond_action，循环对此一无所知。正式命令第一次向模型提供 write_file 和 run_command，第一次能在用户的工作目录里改动文件、执行命令。替代方案：让循环自己处理审批，循环就得知道危险等级和用户界面，被"循环是纯核心"禁止；让每个工具在执行函数里自己请求批准，那要靠自觉，所以改成注册表里的结构性保证，拿不到批准就不调用执行函数；结束命令的进程树用 taskkill，中间进程先退出时它的子进程会漏掉，所以 Windows 上用作业对象。回滚策略：默认工具集回到 read_file 和 list_dir，删除 write_file、run_command 和 Session.respond_action；已经写出的会话记录不需要迁移，批准项的形状从 P3 起就在契约里。
```
