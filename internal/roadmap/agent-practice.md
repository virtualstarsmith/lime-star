# Agent 实践路线图

状态: in_progress
日期: 2026-11-24
主目标: 做出一个能带项目目录读写文件、执行命令、危险操作经审批、会话可恢复的最小 Agent，并全程按本仓库的范式交付。
需求: `../prd/agent-practice.md`（已确认，仓库所有者，2026-11-24）

## 目标

这份路线图是 lime-star 产品开发的主线。它把"做出最小 Agent"拆成 P0 到 P6 七个可以独立验收的阶段，MVP 在 P4 达成；P7 是 MVP 之后的可选扩展。每个阶段都要留下可核对的证据，不靠"做完了"这种叙述。

## 当前事实

- 仓库已建立规则、事实源、计划、验证四层，以及验收方法论和 harness 反馈层的目标骨架，见 `../exec-plans/paradigm-port-plan.md`。
- P0 已于 2026-11-24 交付工程骨架和空命令；P1 已于 2026-11-24 交付多轮对话、请求日志和凭证守卫；P2 已于 2026-11-24 交付回合循环、工具注册表和 read_file（提交 2cc4cbe）；P3 已于 2026-11-24 交付会话记录事实源、第一份回放夹具，并让 read_file 带着路径边界进入正式命令（提交 23c431d）。两个提交随同一次推送，CI 于 2026-11-25 通过。P4 未开始。目标布局见 internal/aiprompts/architecture.md。
- 代码由 Agent 编写，仓库所有者验收；提交按根 AGENTS.md 的提交规则执行。
- 技术栈：Python 3.11 及以上（uv）；OpenAI 兼容模型接口；治理门禁是零依赖的 Node 脚本。
- 需求已于 2026-11-23 重写为行为规格：一个全局文件加五个能力文件，R1 到 R14，见 `../exec-plans/prd-alignment-plan.md`；仓库所有者于 2026-11-24 确认，原有的三个未决问题按推荐答案落成决策。各阶段的"交付需求"引用它的编号，不再复述需求。

## 写集与避让

路线图本身只认领本文件。每个阶段开始时另建阶段计划，并在其中声明该阶段的窄写集。只读避让集固定为：governance 下的基线文件、scripts 根目录的脚本、本文件。

## 删除集

无。路线图不删除任何现有能力。

## 怎么使用这份路线图

每阶段走同一个循环：

1. 你对 Agent 说该阶段的开工话术。
2. Agent 读规则、建阶段计划、实现、跑门禁、写收尾报告。
3. 你按该阶段的"你的验收动作"逐条核对。
4. 通过后你说"提交"，Agent 才 commit；push 需要你单独要求。

每个阶段固定七项：目标、退出条件、证据等级、lime 对照阅读、落地的规则与守卫、你的验收动作、开工话术。

### 通用约定

- 阶段计划命名为 `p<N>-<主题>-plan.md`，放在 `internal/exec-plans/` 下，按 task-plan 模板写。
- 验收动作的统一规则：你亲手跑一次该阶段证据等级要求的命令；抽查一条验证记录能否复现；问 Agent 一个"为什么这样设计，lime 怎么做"的问题。
- 打回条件，任一成立即打回：退出条件没有全部满足；低级证据冒充高级证据；写集越界却没有说明；未验证项没有写原因。
- lime 对照阅读的路径都在 lime 仓库里，只读不改。借鉴的设计按本仓库语境重写，并在阶段计划的来源声明里列出路径。
- 新增 scripts 一级目录（security、smoke、harness）时，在该阶段计划里写明理由，再运行 `node scripts/check-scripts-baseline.mjs --update` 更新冻结基线。
- 用回放夹具取得的 Gate B 证据，必须标注"模型为回放夹具"。
- 每个阶段先读需求的全局文件，再读该阶段"需求文件"列出的能力文件。开工前执行 `rg "^未决 OQ-" internal/prd`：本阶段有未决项时先请仓库所有者答复，不按推荐答案实现。

### 钉死的技术选择

- Python 3.11 及以上，src 布局，包名 lime_star，入口命令 lime-star，依赖与锁文件由 uv 管理。
- 测试用 pytest；检查用 ruff 和 mypy，mypy 对 src 严格、对 tests 放宽。
- 模型用官方 openai SDK 接 OpenAI 兼容接口。地址、密钥、模型名分别读环境变量 LIME_STAR_BASE_URL、LIME_STAR_API_KEY、LIME_STAR_MODEL。
- 请求日志只记关联键、模型名、状态、耗时和 token 用量，不记提示内容和密钥。
- 运行时产物放 .lime-star/，不入库；值得长期回归的样本复制到 tests/fixtures/。

## 阶段总览

| 阶段 | 主题 | 一句话目标 | 证据 | 备注 |
| --- | --- | --- | --- | --- |
| P0 | bootstrap | 工程骨架与空命令 | Gate B | 无 |
| P1 | chat | 接真实模型的多轮对话 | Live + Gate B | 无 |
| P2 | loop-core | 回合循环纯核心与工具注册 | Unit + 入口集成 | 无 |
| P3 | transcript | transcript 成为唯一事实源；read_file 带着路径边界进入正式命令 | Current fixture + Gate A | 仓库所有者于 2026-11-24 把 read_file 从 P4 提前 |
| P4 | tools-approval | 写文件、执行命令、审批 | Gate B | MVP |
| P5 | resume | 中断后接着做 | Gate B | 无 |
| P6 | acceptance-harness | 失败变成资产 | 入口集成 | 无 |
| P7 | 扩展（可选） | 多模型路由、TUI、子 Agent、首个 release | 在阶段计划里确定 | 开始前另立计划 |

## P0 bootstrap：工程起步

### 目标

建立 Python 工程骨架和一条空命令，让门禁从第一天起就覆盖代码。

### 退出条件

交付需求：R1.1、R1.2、R1.3、R1.4。需求文件：`../prd/agent-practice.md`、`../prd/agent-practice/cli.md`。

1. 在干净克隆上 `uv sync` 成功并生成 uv.lock（R1.4）。
2. R1.1 到 R1.3 的场景在真实进程里逐条通过，其中版本号用 `uv run lime-star --version` 验证。
3. verify:local 的任务表包含 lint、typecheck、test:unit、lock 四个 Python 任务，且全部通过。
4. CI 工作流跑通一次。

### 证据等级

- 必须达到：Gate B（真实启动命令并看到输出）。
- 禁止替代：以 pytest 通过冒充进程级证据。

### lime 对照阅读

lime 仓库根 AGENTS.md 的"协议与质量"，以及 internal/aiprompts/quality-workflow.md 的"选择最低门禁"一节：看它如何把改动类型映射到验证命令。

### 落地的规则与守卫

- uv 项目：pyproject.toml 声明 Python 3.11 及以上，使用 src 布局，入口命令 lime-star。
- 开发依赖：pytest、ruff、mypy。
- verify-local.mjs 任务表新增四个任务。lint 跑 `uv run ruff check .` 和 `uv run ruff format --check .`，typecheck 跑 `uv run mypy`，两者由 src/ 与 tests/ 触发。test:unit 跑 `uv run pytest -q`，由 src/、tests/、pyproject.toml、uv.lock 触发。lock 跑 `uv lock --check`，只由 pyproject.toml 触发。
- CI 工作流加入 uv 的安装与 `uv sync`。
- 根 AGENTS.md 的高频命令补 `uv run pytest`、`uv run ruff check`、`uv run mypy`。
- architecture.md 目录地图里 P0 的行从"路线图 P0"改为"已有"。

### 你的验收动作

1. 亲手跑 `uv run lime-star --version`、`uv run lime-star --help`、一个不存在的参数，以及 `npm run verify:local -- --full`。
2. 在 src 里故意放一个未使用的导入，确认 lint 任务失败；删掉后确认通过。
3. 问 Agent：四个 Python 任务各自的触发路径是什么，为什么 lock 只由 pyproject.toml 触发。

### 开工话术

开始 P0。先读 AGENTS.md、internal/aiprompts/architecture.md、internal/prd/agent-practice.md 和 internal/prd/agent-practice/cli.md，声明你的写集，在 internal/exec-plans/ 下新建 p0-bootstrap-plan.md，按路线图 P0 的退出条件实现，完成后按 AGENTS.md 执行方式第 4 条汇报。

## P1 chat：最小对话

### 目标

接上 OpenAI 兼容模型，做出多轮对话命令，并让每次模型请求都留下可关联的记录。

### 退出条件

交付需求：R2.1、R2.2、R3.1 到 R3.3、R4.1 到 R4.6、R12.4 到 R12.6、R13.1 到 R13.13、R14.1 到 R14.4。其中 R14.1 到 R14.4 在本阶段写进系统指令，行为验证在 P4 和 P6。需求文件：`../prd/agent-practice.md`、`../prd/agent-practice/cli.md`、`../prd/agent-practice/turn.md`。

1. 交付需求逐条有验证记录，每条至少一个场景通过。
2. Live：用真实模型连续对话至少三轮，模型记得前面的内容（R2.1-S1）。
3. Gate B：真实 CLI 进程里，请求日志满足 R3.1 到 R3.3，终端输出和日志里搜不到密钥（R4.3）。
4. 密钥守卫脚本通过（R4.5、R4.6）。

### 证据等级

- 必须达到：Live（真实模型）加 Gate B（真实 CLI 进程）。
- 禁止替代：用回放夹具的对话冒充真实模型通过。

### lime 对照阅读

lime 仓库 internal/aiprompts/prompt-foundation.md（基础指令只有一个组装者）和 lime-rs/crates/model-provider 目录的结构（模型边界只做与模型接口相关的事）。

### 落地的规则与守卫

- 根 AGENTS.md 加入凭证硬规则：凭证只放 .env 或环境变量，不得进入代码、文档、测试夹具、transcript 和证据导出。守卫是 scripts/security/check-secrets.mjs：检查 .env 未被 Git 跟踪，已跟踪文件里没有常见密钥格式。
- 新增 .env.example，只含变量名和占位值。
- 新增 scripts/security 一级目录：在 P1 计划里写明理由，再更新冻结基线。
- model_provider 成为 P1 的 current owner。
- app 回合入口在本阶段建立最小形态（start_turn），CLI 只调用它。
- 运行时产物目录 .lime-star 建立，请求日志写入 .lime-star/logs（需求决策 D-29）。

### 你的验收动作

1. 亲手用 `lime-star` 对话三轮。
2. 跑 `git check-ignore .env`，确认密钥文件不在版本库里。
3. 打开请求日志，确认没有提示内容和密钥。
4. 试一次缺少 LIME_STAR_API_KEY 的启动，再在一轮对话进行中按一次 Ctrl+C，核对 R4.2、R12.5、R13.11。
5. 问 Agent：为什么 CLI 不直接调用模型，而要经过 app 回合入口。

### 开工话术

开始 P1。先读 AGENTS.md、internal/aiprompts/architecture.md、internal/aiprompts/governance.md、internal/prd/agent-practice.md、internal/prd/agent-practice/cli.md 和 internal/prd/agent-practice/turn.md，声明你的写集，新建 p1-chat-plan.md，按路线图 P1 的退出条件实现，凭证规则和守卫一起落地，完成后按 AGENTS.md 执行方式第 4 条汇报。

## P2 loop-core：回合循环纯核心与工具注册

### 目标

把"模型决定调用工具、程序执行、结果回填、继续"的循环做成不联网就能测试的纯模块，并建立工具注册表。

### 退出条件

交付需求：R5.1 到 R5.3、R12.1 到 R12.3，以及 R12.4、R12.5 的状态转移部分。需求文件：`../prd/agent-practice.md`、`../prd/agent-practice/turn.md`、`../prd/agent-practice/tools.md`。

1. 回合循环状态机在不联网、不依赖模型客户端的单元测试里覆盖四种转移：继续、达到步数上限（R12.3）、模型出错（R12.4）、用户取消（R12.5）。
2. 工具结果不打断回合（R12.2），循环按 R12.1 的顺序进行。
3. 工具注册表支持按名称注册与查找；每个工具有名称、描述、JSON Schema 参数和执行函数。
4. read_file 可被注册，它的行为满足 R5.1 到 R5.3，在入口集成测试里验证。
5. 循环模块的导入列表里没有模型客户端、工具实现或存储。

### 证据等级

- 必须达到：Unit 加入口集成。
- 禁止替代：用真实模型调用代替不联网的状态机测试。

### lime 对照阅读

lime 仓库 lime-rs/crates/agent-runtime/src/reply_loop.rs（实现约 50 行的纯状态机，连同同文件里的测试共约 86 行）和同目录 provider_turn.rs 的文件头注释（一步一物化的约定）。

### 落地的规则与守卫

- protocol 模块建立：Thread、Turn、Item 的标识与类型（文本、推理、工具调用、工具结果）及其状态。
- 测试目录建立 tests/unit 与 tests/integration。
- architecture.md 追加"Owner 章节：回合循环"，写明循环只依赖 protocol 和工具注册接口。这是新增 owner 章节并确定依赖方向，按重大架构变更填写确认块。

### 你的验收动作

1. 亲手跑 `uv run pytest tests/unit -q`，确认不联网也能全部通过（可以临时断网验证）。
2. 让 Agent 列出循环模块导入了哪些模块，核对没有模型客户端。
3. 问 Agent：达到最大步数时循环怎么退出，用户看到什么。

### 开工话术

开始 P2。先读 AGENTS.md、internal/aiprompts/architecture.md、quality-workflow.md、internal/prd/agent-practice.md、internal/prd/agent-practice/turn.md 和 internal/prd/agent-practice/tools.md，声明你的写集，新建 p2-loop-core-plan.md，按路线图 P2 的退出条件实现，在 architecture.md 追加 Owner 章节和确认块，完成后按 AGENTS.md 执行方式第 4 条汇报。

## P3 transcript：transcript 成为唯一事实源

### 目标

让每一次模型响应和每一次工具结果都落到同一份追加式 transcript，终端显示和证据只能从它派生。read_file 带着路径边界进入正式命令。

### 退出条件

交付需求：R3.4、R6.1 到 R6.7、R11.1、R12.7、R13.14、R13.15，以及 R8.1 到 R8.3 里 read_file 的部分。需求文件：`../prd/agent-practice.md`、`../prd/agent-practice/thread.md`、`../prd/agent-practice/turn.md`、`../prd/agent-practice/cli.md`、`../prd/agent-practice/tools.md`。

1. 交付需求逐条有验证记录，每条至少一个场景通过，其中包括先记录再执行（R6.2）、结果回填后才请求（R6.3）和只凭记录读回（R6.7）。
2. 用录制的模型响应夹具驱动 start_turn，走完"模型请求工具、执行、回填、再请求、结束"的完整主链（R12.1）。
3. 第一条契约登记：protocol 下的 item schema 及其消费者登记进 governance/contracts.json，并通过契约检查。

### 证据等级

- 必须达到：Current fixture 加 Gate A。
- 禁止替代：用真实模型的单次成功对话代替夹具驱动的完整主链测试。

### lime 对照阅读

lime 仓库 internal/aiprompts/query-loop.md 的"固定主链"一节（特别是 TurnInputEnvelope：下游不得重组另一份真实输入），以及 internal/aiprompts/state-history-telemetry.md 的"固定主链"。

### 落地的规则与守卫

- thread_store 成为 current owner：transcript 以 JSONL 追加写在 .lime-star/threads 下。
- model_provider 的请求夹具录制与回放：真实响应录制一次存入 tests/fixtures/provider/，之后默认用回放。
- 契约：protocol 目录建立 item 的 JSON Schema，运行 `node scripts/check-contracts.mjs --update` 登记。
- 行数门禁把 .lime-star 加入排除目录，因为它是运行时产物。
- 根 AGENTS.md 加入硬规则：任何显示、导出或测试不得自己拼第二份会话真相。守卫是 Gate A 测试：read_thread 的结果必须与 transcript 一致。
- architecture.md 追加"Owner 章节：transcript 事实源"。
- read_file 进入正式命令：tool_runtime 的工作目录边界（R8.1 到 R8.3）随它在 P3 落地。list_dir 与 write_file 仍由 P4 交付，并受同一边界约束。

### 你的验收动作

1. 跑一次带工具调用的对话，打开 transcript 文件，确认工具调用和结果在同一份文件里且顺序正确。
2. 亲手跑 `npm run test:contracts`。
3. 抽查一个夹具：问 Agent 它是从哪次真实请求录制的。
4. 问 Agent：为什么工具结果要全部回填之后才进行下一次请求。
5. 让它读工作目录之外的一个文件，确认被拒绝。

### 开工话术

开始 P3。先读 AGENTS.md、internal/aiprompts/architecture.md、internal/tech/harness/README.md、internal/prd/agent-practice.md、internal/prd/agent-practice/thread.md 和 internal/prd/agent-practice/turn.md，声明你的写集，新建 p3-transcript-plan.md，按路线图 P3 的退出条件实现，登记第一条契约，完成后按 AGENTS.md 执行方式第 4 条汇报。

## P4 tools-approval：工具、审批与真实冒烟（MVP）

### 目标

补齐写文件、执行命令和列目录；危险操作必须经用户批准，并用需求里的 MVP 主场景证明 MVP 成立。

### 退出条件

交付需求：R5.4、R7.1 到 R7.13、R8.1 到 R8.3 里 list_dir 与 write_file 的部分、R8.4、R12.5（终止正在运行的命令），并验证 R14.1、R14.2 的行为。需求文件：`../prd/agent-practice.md`、`../prd/agent-practice/tools.md`、`../prd/agent-practice/turn.md`、`../prd/agent-practice/cli.md`。

1. MVP 主场景（见需求全局文件）真实发生：你亲手在 CLI 里完成一次"新建脚本、运行脚本、报告结果"，并至少拒绝一次。
2. 交付需求逐条有验证记录，每条至少一个场景有对应的测试或冒烟断言。
3. Gate B 冒烟脚本通过：真实启动 CLI 进程，自动输入一段多步任务，断言文件变化、命令输出、批准提示（R7.7、R7.8）、拒绝后不执行（R7.10）和终端输出。
4. 按 `../develop/traceable-acceptance.md` 对 MVP 做完整验收，分级结论逐条对应 MVP 范围内的需求。

### 证据等级

- 必须达到：Gate B。
- 禁止替代：用集成测试里函数返回值正确冒充真实进程证据。

### lime 对照阅读

lime 仓库 internal/aiprompts/query-loop.md 里关于 action/respond 与 elicitation 恢复路径的条目（审批是主链上一个可以恢复的节点），以及 lime-rs/crates/tool-runtime 目录的结构（工具定义、权限、执行在同一个 owner）。

### 落地的规则与守卫

- tool_runtime：新增 write_file、run_command、list_dir，它们接上 P3 已有的工作目录边界；危险等级标记（需求决策 D-19）。
- app 回合入口新增 respond_action：批准与拒绝。CLI 负责向用户提问，并把结果交回 app。
- 冒烟脚本 scripts/smoke/agent_gate_b.py：新增 scripts/smoke 一级目录，在 P4 计划里写明理由并更新基线。
- verify-local.mjs 任务表新增 smoke:gate-b，由 src/lime_star/ 触发。
- 根 AGENTS.md 加入审批硬规则：标记为危险的操作必须经 respond_action 批准后才能执行。守卫是冒烟脚本里的拒绝路径断言。
- architecture.md 追加"Owner 章节：工具与审批"。
- quality-workflow.md 最低验证矩阵的"业务主链"一行绑定冒烟命令。

### 你的验收动作

1. 亲手完成 MVP 任务，并在批准提示处至少拒绝一次。
2. 让它尝试写工作目录之外的路径，确认被拒绝。
3. 亲手跑 `uv run python scripts/smoke/agent_gate_b.py`。
4. 问 Agent：批准状态存在哪里；进程在等待批准时退出会怎样。

MVP 在本阶段结束时达成，范围是需求全局文件"MVP 内"一节列出的需求。

### 开工话术

开始 P4。先读 AGENTS.md、internal/aiprompts/architecture.md、internal/aiprompts/quality-workflow.md、internal/prd/agent-practice.md、internal/prd/agent-practice/tools.md、internal/prd/agent-practice/turn.md 和 internal/prd/agent-practice/cli.md，声明你的写集，新建 p4-tools-approval-plan.md，填写验证合同，按路线图 P4 的退出条件实现，完成后按 AGENTS.md 执行方式第 4 条汇报。

## P5 resume：会话恢复

### 目标

进程退出或被中断后，能从 transcript 恢复同一个 thread 并继续。

### 退出条件

交付需求：R9.1 到 R9.5。需求文件：`../prd/agent-practice.md`、`../prd/agent-practice/thread.md`、`../prd/agent-practice/cli.md`。

1. 交付需求逐条有验证记录，每条至少一个场景通过。
2. `lime-star --resume` 在新进程里恢复历史并继续对话（R9.1、R9.2）。
3. 回合进行中按 Ctrl+C 或进程被强制结束，回合被记为中断或被判为中断；恢复后不自动续跑（R9.3、R9.4）。
4. 两种恢复都有 Gate B 证据。

### 证据等级

- 必须达到：Gate B。
- 禁止替代：以直接读取 transcript 文件的单元测试冒充新进程恢复。

### lime 对照阅读

lime 仓库 lime-rs/crates/thread-store 目录的结构（可恢复的 Thread、Turn、Item 读取事实）。

### 落地的规则与守卫

- 根 AGENTS.md 加入持久化硬规则：恢复只能从 thread_store 读取，内存里不保留第二份可恢复状态。守卫是入口集成测试"写入后以新实例读取"。
- architecture.md 追加"Owner 章节：持久化与恢复"。

### 你的验收动作

1. 亲手中断一次并恢复。
2. 问 Agent：恢复时上下文是怎么重建的，哪些内容不会恢复。

### 开工话术

开始 P5。先读 AGENTS.md、internal/aiprompts/architecture.md、internal/aiprompts/quality-workflow.md、internal/prd/agent-practice.md、internal/prd/agent-practice/thread.md 和 internal/prd/agent-practice/cli.md，声明你的写集，新建 p5-resume-plan.md，填写验证合同，按路线图 P5 的退出条件实现，完成后按 AGENTS.md 执行方式第 4 条汇报。

## P6 acceptance-harness：可追踪验收与反馈层

### 目标

把运行事实导出成证据，把失败沉淀成可重放的样本和评测，形成"事实先于解释"的反馈层。

### 退出条件

交付需求：R10.1 到 R10.3、R11.2 到 R11.6，并验证 R14.3、R14.4 的行为。需求文件：`../prd/agent-practice.md`、`../prd/agent-practice/evidence.md`。

1. 交付需求逐条有验证记录，每条至少一个场景通过。
2. internal/tech/harness/README.md 与 internal/test/harness-evals.md 的状态从"未接入"改为"已接入"，并写明实际入口。

### 证据等级

- 必须达到：入口集成。
- 禁止替代：只跑通脚本，不核对导出内容与 transcript 是否一致。

### lime 对照阅读

lime 仓库 internal/develop/traceable-agent-acceptance-methodology.md、internal/test/harness-evals.md、internal/aiprompts/harness-engine-governance.md（数据只准单向流动）。

### 落地的规则与守卫

- scripts/harness 一级目录：证据导出、replay 提升、评测 runner 三个脚本。在 P6 计划里写明理由并更新基线。
- internal/test 下建立任务集 manifest。
- 根 AGENTS.md 加入硬规则：证据、回放、评测只能消费 transcript，不得成为第二份运行事实。守卫是契约测试：证据包里的 item 必须与 transcript 一致。

### 你的验收动作

1. 亲手跑评测 runner，看摘要。
2. 打开导出的证据包，核对一条工具记录。
3. 问 Agent：这条 replay 样本是从哪一次失败来的。

### 开工话术

开始 P6。先读 AGENTS.md、internal/develop/traceable-acceptance.md、internal/tech/harness/README.md、internal/test/harness-evals.md、internal/prd/agent-practice.md 和 internal/prd/agent-practice/evidence.md，声明你的写集，新建 p6-acceptance-harness-plan.md，按路线图 P6 的退出条件实现，完成后按 AGENTS.md 执行方式第 4 条汇报。

## P7 扩展（可选）

### 目标

MVP 之后的扩展候选：多模型路由、TUI、子 Agent、首个 release。

### 退出条件

每做一项之前先另立阶段计划并经仓库所有者确认；该计划的退出条件就是这一项的退出条件。

### 证据等级

在阶段计划里确定；主链改动不得低于 Gate B。

### lime 对照阅读

在阶段计划里按所选项目指定。

### 落地的规则与守卫

- 首个 release 之前，先把 release skill 从骨架补全。
- 每项扩展都要回答：它是否改变业务主链、协议边界或依赖方向；改变即按重大架构变更填写确认块。扩展先落成需求（新增能力文件，或在现有文件里加条目，未决先问），仓库所有者确认需求后再实现。

### 你的验收动作

1. 审阅阶段计划：退出条件是否可观察，证据等级是否足够。
2. 确认这一项扩展和主目标的关系，再决定做还是不做。

### 开工话术

开始 P7 的某一项扩展。先读 AGENTS.md、internal/aiprompts/architecture.md 和路线图，说明它和主目标的关系、是否构成重大架构变更，另立阶段计划交给我确认，确认之后再实现。

## 验证矩阵

| 阶段 | 命令 | 证据等级 | 结果 |
| --- | --- | --- | --- |
| P0 | `uv run lime-star --version`；`npm run verify:local -- --full` | Gate B | 通过（2026-11-24）：本地 8 个任务通过，CI 跑通一次 |
| P1 | `lime-star` 真实对话；密钥守卫脚本 | Live + Gate B | 通过（2026-11-24）：真实模型连续三轮，第三轮答出第一轮说的名字；请求日志三条 ok，没有内容和密钥；密钥守卫通过 |
| P2 | `uv run pytest tests/unit -q` | Unit + 入口集成 | 通过（2026-11-24）：单元测试 89 条，运行前禁用全部 socket；入口集成 30 条、Gate B 回归 35 条，模型都是测试替身；门禁 11 个任务通过。不含 Live。CI 通过（2026-11-25，运行 45515242850） |
| P3 | `npm run test:contracts`；夹具驱动的集成测试 | Current fixture + Gate A | 通过（2026-11-24）：契约 1 项通过；Current fixture 2 条，录制的真实响应不联网走完完整主链；Gate A 9 条。CI 通过（2026-11-25，运行 45515242850） |
| P4 | `uv run python scripts/smoke/agent_gate_b.py` | Gate B | 未跑 |
| P5 | `lime-star --resume`；冒烟脚本 | Gate B | 未跑 |
| P6 | 评测 runner 与 replay 提升脚本 | 入口集成 | 未跑 |

## 验证合同

本文件是路线图，不直接改产品主链，不填验证合同。P1 起的每个主链阶段在自己的阶段计划里填写验证合同。

## 架构确认

路线图本身不改架构。各阶段的架构变更与确认块写在阶段计划和 architecture.md 的 Owner 章节里。

## 进度记录

每完成一个阶段，在这里按日期追加一条：阶段、改动、验证、完成度、下一刀。

### 2026-11-24 P0 bootstrap 完成

- 改动：uv 项目骨架（src 布局、包名 lime_star、入口命令 lime-star），`--version`、`--help` 与未知参数的处理，15 条测试。verify:local 接入 lock、lint、typecheck、test:unit，lock 排在其余 Python 任务之前。CI 加入 uv 的安装与依赖同步。行数守卫跳过 Python 工具的缓存目录。写集、默认选择与验证细节见 `../exec-plans/p0-bootstrap-plan.md`。
- 验证：Gate B 通过。`uv run lime-star --version` 在仓库根与空目录各执行一次，只输出一行版本号，退出码 0；`--help` 退出码 0；`--nosuch` 退出码 2，标准输出为空。`npm run verify:local -- --full` 8 个任务通过。lint 与 lock 的失败探针都被报出。推送后 CI 跑通一次，运行 45302669187，结论 success；依据是运行的分步状态和它留下的 setup-uv 缓存，日志需要登录，没有读。
- 完成度：P0 100%。路线图 14%，P0 完成，P1 到 P7 未开始。
- 下一刀：按 P1 的开工话术开始 P1。技术债 CCD-001 的前提已具备，建议并入 P1 的计划。

### 2026-11-24 P1 chat 完成

- 改动：app 回合入口（start_turn、read_thread）与 model_provider（配置、客户端、系统指令、错误归类、请求日志）落地。`lime-star` 不带参数开始会话，每次请求带上系统指令和到此刻为止的全部历史；请求日志是 `.lime-star/logs/` 下的 JSON Lines，只记时间、标识、状态、耗时和 token 用量；回合出错或被 Ctrl+C 取消后会话可以继续。密钥守卫 `scripts/security/check-secrets.mjs` 接入 verify:local，任务表新增 secrets 与 test:guards。`.env.example`、根 AGENTS.md 的凭证硬规则、architecture.md 的三行状态同步。技术债 CCD-001 清退。写集、默认选择与验证细节见 `../exec-plans/p1-chat-plan.md`。
- 验证：四条退出条件逐条满足。Live：用仓库所有者配置的真实模型（glm-5.2）连续对话三轮，第三轮答出第一轮说的名字（R2.1-S1）；用无效密钥请求真实接口一次，说明为鉴权失败。Gate B：真实进程里请求日志满足 R3.1 到 R3.3，终端输出和日志里搜不到密钥；Ctrl+C 另在真实控制台里用真实事件验证，取消约 0.02 秒生效。密钥守卫通过（R4.5、R4.6）。`npm run verify:local -- --full` 10 个任务通过，117 条通过，2 条 Live 用例默认跳过。推送后 CI 跑通一次，运行 45341894974，结论 success；依据是运行和各步骤的状态，日志需要登录，没有读。架构变更已由仓库所有者确认。
- 完成度：P1 100%。路线图 29%，P0、P1 完成，P2 到 P7 未开始。
- 下一刀：按 P2 的开工话术开始 P2。开工前先定一件事：P1 实测取消一个回合之后，模型会把被取消的那条消息一起回答；要不要把回合结局告诉模型，这决定 P2、P3 怎么设计模型可见的历史。技术债 CCD-002、CCD-003 在 P2 开工前补。

### 2026-11-24 P2 loop-core 交付

- 改动：protocol（项、回合结局、三个边界接口）、agent_runtime 的 run_turn（只依赖 protocol 的纯核心，四种结局）、tool_runtime 的注册表、参数校验和 read_file、model_provider 的 respond、app 的装配。两条架构守卫：导入不越过依赖矩阵，Owner 章节带已签署的确认块；verify-local 新增 architecture 任务，共 11 个。architecture.md 第 4 节的依赖矩阵与 Owner 章节 7.1。正式命令在这一阶段的可见行为与 P1 相同。细节见 `../exec-plans/p2-loop-core-plan.md`。
- 验证：五条退出条件逐条满足。单元测试 89 条，运行前禁用全部 socket，其中循环的 12 条只用 0.05 秒；入口集成 30 条（模型为测试替身）；Gate B 回归 35 条（真实进程，模型为测试替身）。npm run verify:local -- --full 的 11 个任务通过，195 条通过、2 条跳过（Live）。P2 不含 Live 证据。架构确认块已由仓库所有者签署。CI 没有跑：提交 2cc4cbe 还没有推送。
- 完成度：P2 95%，还差 CI。路线图 42%。
- 下一刀：P3 已开工。P2 的计划等 CI 通过后关闭。

### 2026-11-24（路线图调整）

- 仓库所有者说“read_file提到p3，开始P3”：read_file 在 P3 进入正式命令，路径边界 R8.1 到 R8.3 随之提前，但只约束 read_file。P3、P4 的目标、交付需求、落地的规则和验收动作据此改了。P4 仍然交付 list_dir 与 write_file，并让它们受同一边界约束。
- P2 计划里另一件待定的事（取消的回合要不要让模型知道）仓库所有者没有答复，P3 保持现状。

### 2026-11-25 P3 transcript 完成

- 改动：thread_store 把每一项追加进工作目录下 .lime-star/threads 的 JSON Lines 文件并落盘，只凭文件读回；read_thread 与终端显示只从它派生，app 不再在内存里留第二份。循环写下回合的开始与结局，给没有执行的调用补一条出错的结果。read_file 带着工作目录边界进入正式命令。从真实模型录制了第一份回放夹具，测试默认回放。契约 thread-items 登记；根 AGENTS.md 加入“不得自己拼第二份会话真相”的硬规则；architecture.md 的目录地图与 Owner 章节 7.2。细节见 `../exec-plans/p3-transcript-plan.md`。
- 验证：三条退出条件逐条满足。Current fixture：录制的真实响应（模型 glm-5.2）驱动 start_turn 走完“模型请求工具、执行、回填、再请求、结束”，不联网。Gate A：只凭文件核对会话记录的 9 条用例。单元测试 139 条，运行前禁用全部 socket；入口集成 46 条、Gate B 回归 23 条，模型都是测试替身。交付的需求逐条有验证记录，对应表在计划里。本地门禁 11 个任务通过，260 条通过、2 条跳过（Live）。Live 只有录制那一次，共 4 次真实请求。架构确认块已由仓库所有者签署。
- CI：推送后跑通一次，运行 45515242850，针对提交 23c431d，结论 success。verify 作业的 Local gate (full) 在 Linux runner 上通过，这是 P2 与 P3 的代码第一次在 Windows 以外运行。依据是运行、作业和步骤的状态，日志没有读。P2 的提交 2cc4cbe 包含在这次推送里，上一条记录里“CI 没有跑”由此补上，P2 也记为完成。
- 完成度：P3 100%，P2 100%。路线图 57%，P0 到 P3 完成，P4 到 P7 未开始。
- 下一刀：按 P4 的开工话术开始 P4。开工前有一件事最好先定：取消的回合要不要让模型知道。P2 和 P3 的计划里都提过，仓库所有者还没有答复；P4 的写文件和执行命令会让它更要紧。P4 还要带上 P3 的两条观察：自动化脚本以输入提示为同步点，不是回复文本；模拟的 Ctrl+C 打不断一次长的阻塞，run_command 要按切片等待。

## 当前结论

完成度: 57%（P0 到 P3 完成；P4 到 P7 未开始）
