# Agent 实践路线图

状态: in_progress
日期: 2026-11-23
主目标: 做出一个能带项目目录读写文件、执行命令、危险操作经审批、会话可恢复的最小 Agent，并全程按本仓库的范式交付。
需求: `../prd/agent-practice.md`（草稿，待仓库所有者确认）

## 目标

这份路线图是 lime-star 产品开发的主线。它把"做出最小 Agent"拆成 P0 到 P6 七个可以独立验收的阶段，MVP 在 P4 达成；P7 是 MVP 之后的可选扩展。每个阶段都要留下可核对的证据，不靠"做完了"这种叙述。

## 当前事实

- 仓库已建立规则、事实源、计划、验证四层，以及验收方法论和 harness 反馈层的目标骨架，见 `../exec-plans/paradigm-port-plan.md`。
- 产品代码尚未开始；目标布局见 internal/aiprompts/architecture.md。
- 代码由 Agent 编写，仓库所有者验收；提交按根 AGENTS.md 的提交规则执行。
- 技术栈：Python 3.11 及以上（uv）；OpenAI 兼容模型接口；治理门禁是零依赖的 Node 脚本。

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
| P3 | transcript | transcript 成为唯一事实源 | Current fixture + Gate A | 无 |
| P4 | tools-approval | 写文件、执行命令、审批 | Gate B | MVP |
| P5 | resume | 中断后接着做 | Gate B | 无 |
| P6 | acceptance-harness | 失败变成资产 | 入口集成 | 无 |
| P7 | 扩展（可选） | 多模型路由、TUI、子 Agent、首个 release | 在阶段计划里确定 | 开始前另立计划 |

## P0 bootstrap：工程起步

### 目标

建立 Python 工程骨架和一条空命令，让门禁从第一天起就覆盖代码。

### 退出条件

1. 在干净克隆上 `uv sync` 成功并生成 uv.lock。
2. `uv run lime-star --version` 在真实进程里输出版本号。
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

1. 亲手跑 `uv run lime-star --version` 和 `npm run verify:local -- --full`。
2. 在 src 里故意放一个未使用的导入，确认 lint 任务失败；删掉后确认通过。
3. 问 Agent：四个 Python 任务各自的触发路径是什么，为什么 lock 只由 pyproject.toml 触发。

### 开工话术

开始 P0。先读 AGENTS.md 和 internal/aiprompts/architecture.md，声明你的写集，在 internal/exec-plans/ 下新建 p0-bootstrap-plan.md，按路线图 P0 的退出条件实现，完成后按 AGENTS.md 执行方式第 4 条汇报。

## P1 chat：最小对话

### 目标

接上 OpenAI 兼容模型，做出多轮对话命令，并让每次模型请求都留下可关联的记录。

### 退出条件

1. 用真实模型连续对话至少三轮，模型记得前面的内容。
2. 每次模型请求在请求日志里有一条记录，含 session_id、thread_id、turn_id、request_id、模型名、状态、耗时和 token 用量；不含提示内容和密钥。
3. 密钥从环境变量或 .env 读取，.env 不入库，密钥守卫脚本通过。

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
- 运行时产物目录 .lime-star 建立，请求日志写入 .lime-star/logs。

### 你的验收动作

1. 亲手用 `lime-star` 对话三轮。
2. 跑 `git check-ignore .env`，确认密钥文件不在版本库里。
3. 打开请求日志，确认没有提示内容和密钥。
4. 问 Agent：为什么 CLI 不直接调用模型，而要经过 app 回合入口。

### 开工话术

开始 P1。先读 AGENTS.md、internal/aiprompts/architecture.md 和 internal/aiprompts/governance.md，声明你的写集，新建 p1-chat-plan.md，按路线图 P1 的退出条件实现，凭证规则和守卫一起落地，完成后按 AGENTS.md 执行方式第 4 条汇报。

## P2 loop-core：回合循环纯核心与工具注册

### 目标

把"模型决定调用工具、程序执行、结果回填、继续"的循环做成不联网就能测试的纯模块，并建立工具注册表。

### 退出条件

1. 回合循环状态机在不联网、不依赖模型客户端的单元测试里覆盖四种转移：继续、达到最大步数、模型出错、用户取消。
2. 工具注册表支持按名称注册与查找；每个工具有名称、描述、JSON Schema 参数和执行函数。
3. read_file 工具可被注册，并在入口集成测试里被调用。
4. 循环模块的导入列表里没有模型客户端、工具实现或存储。

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

开始 P2。先读 AGENTS.md、internal/aiprompts/architecture.md 和 quality-workflow.md，声明你的写集，新建 p2-loop-core-plan.md，按路线图 P2 的退出条件实现，在 architecture.md 追加 Owner 章节和确认块，完成后按 AGENTS.md 执行方式第 4 条汇报。

## P3 transcript：transcript 成为唯一事实源

### 目标

让每一次模型响应和每一次工具结果都落到同一份追加式 transcript，终端显示和证据只能从它派生。

### 退出条件

1. 模型的每次响应先落成 item，再进入下一步处理。
2. 一次响应里的全部工具调用执行完后，结果写回同一份 transcript，之后才发起下一次模型请求。
3. app 回合入口能从 transcript 还原 thread 的 item 列表。
4. 用录制的模型响应夹具驱动 start_turn，走完"模型请求工具、执行、回填、再请求、结束"的完整主链。
5. 第一条契约登记：protocol 下的 item schema 及其消费者登记进 governance/contracts.json，并通过契约检查。

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

### 你的验收动作

1. 跑一次带工具调用的对话，打开 transcript 文件，确认工具调用和结果在同一份文件里且顺序正确。
2. 亲手跑 `npm run test:contracts`。
3. 抽查一个夹具：问 Agent 它是从哪次真实请求录制的。
4. 问 Agent：为什么工具结果要全部回填之后才进行下一次请求。

### 开工话术

开始 P3。先读 AGENTS.md、internal/aiprompts/architecture.md 和 internal/tech/harness/README.md，声明你的写集，新建 p3-transcript-plan.md，按路线图 P3 的退出条件实现，登记第一条契约，完成后按 AGENTS.md 执行方式第 4 条汇报。

## P4 tools-approval：工具、审批与真实冒烟（MVP）

### 目标

补齐写文件和执行命令两个工具，危险操作必须经用户批准，并用一个真实任务证明 MVP 成立。

### 退出条件

1. 你亲手在 CLI 里完成一次"让它新建脚本、运行脚本、报告结果"。
2. 写文件和执行命令被标为危险操作，执行前出现批准提示；被拒绝后不执行，且 transcript 记录拒绝。
3. 文件路径限定在工作目录内，越界访问被拒绝。
4. Gate B 冒烟脚本通过：真实启动 CLI 进程，自动输入一段多步任务，断言文件变化、命令输出、批准提示和终端输出。

### 证据等级

- 必须达到：Gate B。
- 禁止替代：用集成测试里函数返回值正确冒充真实进程证据。

### lime 对照阅读

lime 仓库 internal/aiprompts/query-loop.md 里关于 action/respond 与 elicitation 恢复路径的条目（审批是主链上一个可以恢复的节点），以及 lime-rs/crates/tool-runtime 目录的结构（工具定义、权限、执行在同一个 owner）。

### 落地的规则与守卫

- tool_runtime：新增 write_file、run_command；工作目录边界校验；危险等级标记。
- app 回合入口新增 respond_action：批准与拒绝。CLI 负责向用户提问，并把结果交回 app。
- 冒烟脚本 scripts/smoke/agent_gate_b.py：新增 scripts/smoke 一级目录，在 P4 计划里写明理由并更新基线。
- verify-local.mjs 任务表新增 smoke:gate-b，由 src/lime_star/ 触发。
- 根 AGENTS.md 加入审批硬规则：标记为危险的操作必须经 respond_action 批准后才能执行。守卫是冒烟脚本里的拒绝路径断言。
- architecture.md 追加"Owner 章节：工具与审批"。
- quality-workflow.md 最低验证矩阵的"业务主链"一行绑定冒烟命令。

### 你的验收动作

1. 亲手完成 MVP 任务，并在批准提示处至少拒绝一次。
2. 让它尝试读工作目录之外的文件，确认被拒绝。
3. 亲手跑 `uv run python scripts/smoke/agent_gate_b.py`。
4. 问 Agent：批准状态存在哪里；进程在等待批准时退出会怎样。

MVP 在本阶段结束时达成。之后按 internal/develop/traceable-acceptance.md 对 MVP 做一次完整验收，并给出分级结论。

### 开工话术

开始 P4。先读 AGENTS.md、internal/aiprompts/architecture.md 和 internal/aiprompts/quality-workflow.md，声明你的写集，新建 p4-tools-approval-plan.md，填写验证合同，按路线图 P4 的退出条件实现，完成后按 AGENTS.md 执行方式第 4 条汇报。

## P5 resume：会话恢复

### 目标

进程退出或被中断后，能从 transcript 恢复同一个 thread 并继续。

### 退出条件

1. `lime-star --resume` 在新进程里恢复历史并继续对话。
2. 回合进行中按 Ctrl+C，thread 和 turn 被记为中断；恢复后可以继续。
3. 两种恢复都有 Gate B 证据。

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

开始 P5。先读 AGENTS.md、internal/aiprompts/architecture.md 和 internal/aiprompts/quality-workflow.md，声明你的写集，新建 p5-resume-plan.md，填写验证合同，按路线图 P5 的退出条件实现，完成后按 AGENTS.md 执行方式第 4 条汇报。

## P6 acceptance-harness：可追踪验收与反馈层

### 目标

把运行事实导出成证据，把失败沉淀成可重放的样本和评测，形成"事实先于解释"的反馈层。

### 退出条件

1. 证据导出：从 transcript 生成一个会话的证据包，含时间线、工具与命令结果、警告和真实发生过的验证记录。
2. 一次真实失败被提升为仓库内的 replay 四件套：input、expected、grader、evidence-links。
3. 评测 runner 读取任务集 manifest，对至少一条固定样本产出 JSON 与 Markdown 摘要。
4. internal/tech/harness/README.md 与 internal/test/harness-evals.md 的状态从"未接入"改为"已接入"，并写明实际入口。

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

开始 P6。先读 AGENTS.md、internal/develop/traceable-acceptance.md、internal/tech/harness/README.md 和 internal/test/harness-evals.md，声明你的写集，新建 p6-acceptance-harness-plan.md，按路线图 P6 的退出条件实现，完成后按 AGENTS.md 执行方式第 4 条汇报。

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
- 每项扩展都要回答：它是否改变业务主链、协议边界或依赖方向；改变即按重大架构变更填写确认块。

### 你的验收动作

1. 审阅阶段计划：退出条件是否可观察，证据等级是否足够。
2. 确认这一项扩展和主目标的关系，再决定做还是不做。

### 开工话术

开始 P7 的某一项扩展。先读 AGENTS.md、internal/aiprompts/architecture.md 和路线图，说明它和主目标的关系、是否构成重大架构变更，另立阶段计划交给我确认，确认之后再实现。

## 验证矩阵

| 阶段 | 命令 | 证据等级 | 结果 |
| --- | --- | --- | --- |
| P0 | `uv run lime-star --version`；`npm run verify:local -- --full` | Gate B | 未跑 |
| P1 | `lime-star` 真实对话；密钥守卫脚本 | Live + Gate B | 未跑 |
| P2 | `uv run pytest tests/unit -q` | Unit + 入口集成 | 未跑 |
| P3 | `npm run test:contracts`；夹具驱动的集成测试 | Current fixture + Gate A | 未跑 |
| P4 | `uv run python scripts/smoke/agent_gate_b.py` | Gate B | 未跑 |
| P5 | `lime-star --resume`；冒烟脚本 | Gate B | 未跑 |
| P6 | 评测 runner 与 replay 提升脚本 | 入口集成 | 未跑 |

## 验证合同

本文件是路线图，不直接改产品主链，不填验证合同。P1 起的每个主链阶段在自己的阶段计划里填写验证合同。

## 架构确认

路线图本身不改架构。各阶段的架构变更与确认块写在阶段计划和 architecture.md 的 Owner 章节里。

## 进度记录

每完成一个阶段，在这里按日期追加一条：阶段、改动、验证、完成度、下一刀。

## 当前结论

完成度: 0%（P0 到 P7 均未开始）
