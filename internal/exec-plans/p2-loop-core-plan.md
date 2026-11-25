# p2-loop-core 计划

状态: done
日期: 2026-11-24
主目标: 把"模型决定调用工具、程序执行、结果回填、继续"的回合循环做成不联网就能测试的纯核心，建立工具注册表，并让 read_file 可被注册。

## 目标

回合循环是一个只依赖 protocol 的纯模块，四种转移（继续到完成、步数上限、模型出错、用户取消）在不联网、不依赖模型客户端的单元测试里各有覆盖；工具注册表能按名称注册与查找，每个工具有名称、描述、JSON Schema 参数和执行函数；read_file 可被注册并满足 R5.1 到 R5.3，从 app 回合入口驱动时走通"模型请求工具、执行、回填、再请求、结束"。正式命令在这一阶段的可见行为与 P1 相同。技术债 CCD-002、CCD-003 在本阶段补上守卫。

## 当前事实

- 仓库所有者于 2026-11-24 说"开始P2"。开工前检索未决项（rg "^未决 OQ-" internal/prd），没有命中。路线图 P2 交付的需求编号和证据等级见 `../roadmap/agent-practice.md`，这里不复述。
- P1 留下的形态：Session.start_turn 只发一次模型请求；会话历史是 app 内存里的 Message（用户、模型两种）加回合结局，经 read_thread 读取；Provider.complete 收 Message 序列，只取出回复文本。目录地图里 protocol、agent_runtime、tool_runtime 三项登记为"路线图 P2"，落地前不存在。
- 路线图 P1 的阶段结论留下一件开工前要定的事：取消一个回合之后，模型会把被取消的那条消息一起回答；要不要把回合结局告诉模型。这要仓库所有者决定，本计划不替他决定。P2 不改变模型可见历史的现状，并把"会话记录转成线路消息"的转换收在模型边界的一处，之后无论怎么定都只改那一处。见下面"待仓库所有者决定"。
- 技术债 CCD-002 要求首次追加 Owner 章节之前补确认块守卫，CCD-003 要求 agent_runtime 落地之前补导入边界守卫，两条都要挂进 verify-local 任务表。所以守卫排在本阶段最前面。
- 本机环境：uv 0.12.4、Python 3.14.5、Node 25.2.1、Windows PowerShell 5.1；模型 SDK 是 openai 3.58.0。
- lime 对照阅读（只读，仓库位置见 architecture.md）：lime-rs/crates/agent-runtime/src/reply_loop.rs 是一个只记"已经试了几次"的纯状态结构，每进一步给出"继续"或"达到上限"两种结果；同目录 provider_turn.rs 的文件头注释写明，每次响应先落成文本、推理、工具调用，工具全部完成后把结果追加到同一份记录，再开始下一次请求，线路细节留在模型边界，工具执行留在工具边界。另为两条守卫看了 scripts/check-import-boundaries.mjs 与 scripts/governance/check-architecture-confirmation.mjs 的做法。本计划据此让循环只通过 protocol 里的接口与外界往来；守卫没有照搬 lime 面向 PR 的做法，改为检查本仓库自己的产物（架构图里的依赖矩阵与 Owner 章节、源码的导入）。没有复制原文。

## 写集与避让

### 本轮认领写集

新建：

- src/lime_star/protocol/ 下的 __init__.py、items.py、turn.py
- src/lime_star/agent_runtime/ 下的 __init__.py、loop.py
- src/lime_star/tool_runtime/ 下的 __init__.py、registry.py、schema.py、read_file.py
- tests/unit/ 下的 test_loop.py、test_registry.py、test_read_file.py
- tests/integration/ 下的 test_loop.py、test_tools.py、test_guard_architecture.py
- 本计划

修改：

- src/lime_star/model_provider/provider.py 与 __init__.py：历史改用协议里的项，请求带上工具定义，响应取出工具调用。
- src/lime_star/app/session.py 与 __init__.py：回合交给循环；会话记录改为项。
- src/lime_star/cli/chat.py：显示步数上限这种结局。
- tests/integration/ 下的 fake_model.py、conftest.py、test_turn.py、test_cli_process.py。
- scripts/verify-local.mjs：任务表新增 architecture。它是共享热区里的根脚本，本轮没有其他 Agent 在工作，改动只有任务表里的一项。
- internal/aiprompts/architecture.md（共享热区）：目录地图三行的状态、第 4 节的依赖矩阵、第 7 节的 Owner 章节 7.1 与确认块。第 4 节的第一条按矩阵改写了：原文的链条读起来像 app 只经 agent_runtime 才到模型边界，与 P1 起 app 直接装配模型边界的事实不符。
- internal/aiprompts/governance.md：守卫表补两行。
- scripts/README.md、根 README.md、本目录的 README.md。
- tech-debt-tracker.md：CCD-002、CCD-003 清退。

### 只读避让写集

- ../roadmap/agent-practice.md：路线图规定它是只读避让集，阶段结论等仓库所有者验收后再追加。
- ../prd/：需求已确认，不改。
- governance/ 下的基线与契约清单：本轮不新增 scripts 目录，也不登记契约，基线不变。
- scripts 下其余脚本，.github/workflows/quality.yml：门禁经 verify-local 运行，不需要改。
- src/lime_star/thread_store/ 与仓库根的 protocol/：属于 P3，落地前不创建。P2 的会话记录仍是 app 内存里的项，不落盘。

## 删除集

- Provider.complete，以及 model_provider 包导出的 Message、ModelError、Reply：由 Provider.respond 和协议里的 ModelReply、ModelFailure 与各项取代。
- Record.messages：由 Record.items 取代。
- app 里 Outcome 与 TurnResult 的定义：挪进 protocol，app 照旧导出这两个名字，调用处不用改。
- 用例 test_three_requests_under_one_turn_get_distinct_request_ids 在模型边界上的写法：改为从回合入口经真实的循环验证，用例名不变。

## 本阶段的默认选择

1. 正式命令在 P2 不向模型提供任何工具。open_session 的 tools 留空时注册表为空，请求里不带 tools 字段，所以正式命令发出的请求与 P1 相同。read_file 只在入口集成测试里经 open_session 的 tools 参数注册。落选的备选：现在就把 read_file 挂到正式命令上。落选原因：R13.14、R13.15 的显示、R6 的会话记录和 R8 的路径边界都还没有交付，模型读文件时用户看不到、没有记录，路径也不受边界约束。
2. 循环只通过 protocol 里的三个接口与外界往来：模型（respond）、工具集（specs、execute）、会话记录（append）。接口是结构化类型，由 app 回合入口装配。落选的备选：循环直接导入 Provider 和 Registry，违反第 4 节的依赖方向；把循环写成产出动作的生成器、由 app 驱动，P4 的审批需要可暂停，届时再评估是否改写。
3. 一次模型响应落成项的顺序固定：推理、文本、工具调用。
4. 第 20 次响应仍调用工具时：这次响应里的项照常写进记录，工具一个也不执行，回合以步数上限结束（R12.3-S1）。
5. 模型出错与工具出错是两种处理：模型请求失败结束回合（R12.4，不重试）；工具出错、未知工具、参数不合法都作为工具结果交回模型，回合继续（R12.2）。
6. 取消时，已经写进记录的项留着；被中断的那次工具调用没有结果项，也不补写。落选的备选：为没有执行的调用补一条"已取消"的结果。落选原因：这是会话记录与模型可见历史的设计，应当随"要不要把回合结局告诉模型"一起定。P2 的正式命令没有工具，这种情况只在测试注入工具时出现。达到步数上限时最后一次响应里的调用也一样没有结果，见进度记录里“观察到但没有处理”的第 2 条。
7. 参数校验只解释 JSON Schema 的四个关键字：type、properties、required、items。模型给出的参数原文原样记在项里，解析和校验在工具边界做；空串当作没有参数。
8. 接口返回的工具调用缺少 id 时，按它在响应里的序号补一个 call<n>。这一点没有在真实接口上验证。
9. 协议里有推理项，循环会把它写进记录；P2 的模型边界不提取推理内容，也不回传。原因：各家接口的字段名和回传规则不一致，P2 的证据等级不含 Live，没有对过真实接口。
10. 会话记录在 P2 仍是 app 内存里的项，经 read_thread 读取。项没有标识、序号和时间，标识也仍是普通字符串；这些随 P3 的 thread_store 和 item schema 定型。
11. read_file 的细节：行号右对齐占 6 位，后面跟两个空格；LF、CRLF、CR 都算换行；UTF-8 BOM 不计入内容；空文件返回"（空文件）"；被截断时在末尾加一行说明。路径相对工作目录解析，绝对路径按原样；路径边界 R8 属于 P4。
12. 两个守卫写成 pytest 用例，不新增 scripts 脚本。依赖方向要用 Python 的 ast 解析导入，零依赖的 Node 脚本只能做文本匹配。依赖矩阵从 architecture.md 第 4 节的表里读，文档是唯一来源。verify-local 新增任务 architecture，由产品代码、架构图或守卫本身的改动触发。落选的备选：新增 scripts/architecture/ 目录放 Python 脚本，那要多一个基线条目、一组进程级回归用例和一层进程开销。
13. 架构确认守卫是严格的：Owner 章节没有确认块、确认块未签署或仍是占位符，门禁一律失败。所以本阶段在仓库所有者确认之前，全量 pytest 与 verify-local 会失败，这是规则"未确认的重大变更不得标记完成"的机械表现。定向命令不受影响。
14. 步数上限的说明写在标准输出，它不是错误；终端文案是"回合结束：已达到步数上限（一个回合最多 20 次模型请求）。"
15. P2 不跑 Live。P2 的证据等级是 Unit 加入口集成；主链改动用真实进程、模型为测试替身的用例做回归。
16. 入口用例里模拟 Ctrl+C 的测试工具按 0.1 秒的切片等待。模拟的中断打不断一次长的阻塞，只在上一个字节码边界生效，切片让取消在一个切片内生效。落选的备选：一次等 30 秒，实测取消要等满 30 秒才生效。

## 待仓库所有者决定

1. 取消的回合要不要让模型知道（路线图 P1 的阶段结论留下的待定项）。P2 保持现状：取消的回合里，用户消息留在历史里，不附加任何说明。这个决定影响 P3：R6.4 要求记录的就是交给模型的，所以无论选哪一种，告诉模型的内容都要先在会话记录里，建议在 P3 设计回合结局项（R12.7）时一并定。
2. read_file 何时进入正式命令。P3 的验收动作要求亲手跑一次带工具调用的对话，而路径边界 R8 排在 P4。要么把 R8.1 到 R8.3 提前到 P3 一起做，要么接受 P3 到 P4 之间正式命令能读工作目录之外的文件。这是路线图的排序，本计划不改。

## 阶段与退出条件

### A 守卫（技术债 CCD-002、CCD-003）

- 退出条件：架构守卫在仓库自身上运行，并用临时目录里的违例树与合成文档证明它会报出这些情况：cli 导入模型边界，循环导入模型客户端 SDK 或工具实现，未登记的包，缺确认块，未签署或仍是占位符的确认块，引用了不存在的章节，确认内容缺替代方案或回滚策略。改动 src/lime_star/、architecture.md 或守卫文件时，verify-local 选中 architecture 任务。技术债表里 CCD-002、CCD-003 标为 closed。

### B 协议与回合循环

- 退出条件：tests/unit/test_loop.py 不联网、不依赖模型客户端，覆盖四种转移：继续（R12.1）、步数上限（R12.3-S1）、模型出错（R12.4）、用户取消（R12.5-S2）；工具出错不打断回合（R12.2）；一次响应里的工具全部执行完、结果都写回之后才发起下一次请求（R12.1-S2）；响应里的项先写进记录再执行工具；循环模块的导入只有 protocol 和标准库。

### C 工具注册表与 read_file

- 退出条件：注册表支持按名称注册与查找，重名报错；未知工具、参数不合法、工具运行时出错都得到出错的结果，不向外抛异常；read_file 的单元测试覆盖 R5.1-S1、R5.1-S2、R5.2-S1、R5.3-S1、R5.3-S2 和文件不存在（R12.2-S1）。

### D 接入主链

- 退出条件：从 open_session 与 start_turn 驱动、模型为测试替身时，带工具调用的回合按"请求工具、执行、回填、再请求、结束"走通，第二次请求里有工具调用和结果（R12.1-S1、R12.1-S2）；read_file 的五个场景在入口集成里各有通过的用例（R5.1 到 R5.3）；read_file 读不存在的文件时模型收到"文件不存在"，回合没有结束（R12.2-S1）；一个回合里的 20 次请求留下 20 条记录，request_id 互不相同（R3.1-S1），结局是步数上限；不注册工具的会话发出的请求里没有 tools 字段；P1 的进程用例和控制台用例照常通过。

### E 收尾

- 退出条件：architecture.md 的目录地图、依赖矩阵、Owner 章节 7.1 与确认块备好；governance.md、两个 README、本目录的 README 和技术债表同步；ruff 与 mypy 通过；路线图 P2 的五条退出条件逐条有结果。

## 验证矩阵

| 阶段 | 命令 | 证据等级 | 结果 |
| --- | --- | --- | --- |
| A | uv run pytest tests/integration/test_guard_architecture.py -q | 守卫（仓库自身，加临时目录里的反例） | 签署后 21 条通过。签署之前 test_owner_chapters_carry_a_signed_confirmation_block 按设计失败，它报 Owner 章节 7.1 的确认块“实际是：待确认”，见进度记录 2026-11-24 的两条 |
| A | node scripts/verify-local.mjs --dry-run 加各组路径 | 门禁（任务选择） | 通过：改 src/lime_star/ 下的文件选中 lint、typecheck、test:unit、architecture；改 architecture.md 选中 doc-links 与 architecture；改守卫文件选中 test:unit、test:guards、architecture；只改别的文档时不选它；--full 选中 11 个任务 |
| B | uv run pytest tests/unit/test_loop.py -q | Unit（不联网，模型是脚本） | 通过：12 条，0.05 秒 |
| C | uv run pytest tests/unit/test_registry.py tests/unit/test_read_file.py -q | Unit | 通过：26 条 |
| D | uv run pytest tests/integration/test_turn.py tests/integration/test_loop.py tests/integration/test_tools.py -q | 入口集成（模型为测试替身） | 通过：30 条 |
| D | uv run pytest tests/integration/test_cli_process.py tests/integration/test_cli_chat.py tests/integration/test_cli_console.py -q | Gate B 回归（真实进程，模型为测试替身；控制台用例含真实 Ctrl+C 事件） | 通过：35 条，其中新增 1 条步数上限的终端说明，其余是 P1 的 |
| 全程 | uv run pytest tests/unit -q，运行前把 socket 的构造函数换成直接抛错 | Unit | 通过：89 条，1.66 秒。禁用本身经过确认：同一个禁用下创建连接确实被拦下 |
| 全程 | uv run pytest -q | 汇总 | 签署后 195 条通过，2 条跳过（Live）。签署之前另有 1 条失败，就是确认块守卫 |
| 全程 | uv run ruff check . 与 uv run ruff format --check . | 静态检查 | 通过：88 个文件 |
| 全程 | uv run mypy，另按 Linux 平台口径跑一次 | 类型检查 | 通过：47 个文件 |
| 全程 | 密钥守卫的 8 条规则，对本轮新增和修改的 33 个文件另扫一遍 | 守卫 | 通过：0 处命中。正式的密钥守卫只扫已跟踪的文件，本轮的新文件要等提交后才在它的范围内 |
| E | npm run verify:local -- --full | 门禁 | 通过：签署后的工作树上 11 个任务全部通过，test:unit 里 195 条通过、2 条跳过（Live），test:guards 41 条，architecture 21 条。签署之前它停在 test:unit 的确认块守卫上，见进度记录 2026-11-24 |
| P2 | Live（真实模型） | Live | 不跑：P2 的证据等级是 Unit 加入口集成，主链回归用真实进程加测试替身；真实模型会消耗仓库所有者的额度 |

## 验证合同

预算标签: budget:normal（定向测试加门禁）

主链: app 回合入口 start_turn -> agent_runtime 回合循环 -> model_provider 的一次请求 / tool_runtime 的一次工具执行 -> 会话记录（P2 为 app 内存里的项）-> CLI 投影

Happy Path:

1. 配置齐全，经 open_session 打开会话。入口集成测试经 tools 参数注册 read_file，正式命令不注册任何工具。
2. 用户提交一条消息。回合循环把它写进记录，带上到此刻为止的全部项和可用工具，发起一次模型请求。
3. 模型请求调用 read_file。循环先把这次响应落成项并写进记录，再执行工具，结果写进记录。
4. 循环发起下一次请求，历史里有工具调用和它的结果。模型给出不含工具调用的回复，回合以完成结束。
5. 用户看到最终回复，回到输入提示。

Evidence Layers:

- 必须达到: Unit（回合循环的状态转移，不联网、不依赖模型客户端）加入口集成（从 open_session 与 start_turn 驱动，模型为测试替身）。
- 禁止替代: 用真实模型调用代替不联网的状态机测试；单元测试冒充入口集成；测试替身冒充真实模型。P1 已交付主链的回归证据是真实进程加测试替身，按 Gate B 回归报告，并注明模型为测试替身。

必跑命令:

| 命令 | 目的 | 状态 |
| --- | --- | --- |
| uv run pytest tests/unit -q | 循环、注册表、read_file 的纯逻辑，不联网 | 通过：89 条 |
| uv run pytest tests/integration/test_turn.py tests/integration/test_loop.py tests/integration/test_tools.py -q | 入口集成：循环接线、read_file 的五个场景、步数上限、取消 | 通过：30 条 |
| uv run pytest tests/integration/test_cli_process.py tests/integration/test_cli_chat.py tests/integration/test_cli_console.py -q | 主链回归与步数上限的终端文案 | 通过：35 条 |
| uv run pytest tests/integration/test_guard_architecture.py -q | 两条架构守卫 | 签署后 21 条通过；签署之前确认块那一条按设计失败 |
| uv run ruff check . 与 uv run ruff format --check . | 静态检查 | 通过 |
| uv run mypy | 类型检查 | 通过 |
| npm run verify:local -- --full | 本地门禁 | 通过：签署后的工作树上 11 个任务 |

必跑命令里没有 Live，原因见验证矩阵。

失败回写: 测试失败时三选一，修产品、修测试、补守卫。本轮的记录：

- 补守卫。守卫自己的用例抓到它三个毛病：把包导入自己包里的模块当成违例；在 model_provider 里也报模型 SDK；违例说明里少了分隔符。三处都改了守卫，用例没有改。
- 修产品。守卫在仓库自身上报出 app/session.py 为了标注注入的客户端导入了 openai。改法是 model_provider 导出 Client 类型，app 用它标注，不再导入 SDK。
- 修产品。参数不合法的说明里，英文参数名和后面的中文之间没有分隔（“参数 path应当是”），改成“参数 path：应当是”。
- 修测试和夹具，产品行为没有为这些失败改动：循环用例把会话记录的 append 方法当成记录本身传了进去；两处下标把请求数错了；替身模型补上带工具调用的响应，并记下请求的顶层字段名，用来证明没有 tools 字段。
- ruff 与 mypy 报出的问题按修产品和修测试处理：这个版本的 SDK 用 omit 而不是 NOT_GIVEN 表示“不出这个参数”；工具定义和工具调用参数的函数类型各在一个单独的模块里；参数模式的类型要对上接口声明的 dict[str, object]。

完成标准:

- [x] 必跑命令全部有结果记录
- [x] 证据等级达到 Evidence Layers 要求：Unit 与入口集成都已达到
- [x] 下一刀已写明

## 架构确认

```text
Architecture impact: major
架构图已更新：architecture.md 第 2 节目录地图（protocol、agent_runtime、tool_runtime 三行的状态列）、第 4 节的依赖矩阵、第 7 节的 Owner 章节 7.1
Responsible developer confirmation: 仓库所有者，2026-11-24
确认内容：本阶段新增 protocol、agent_runtime、tool_runtime 三个 owner，回合入口第一次把回合交给循环，模型请求第一次能带上工具定义并取回工具调用。循环是只依赖 protocol 的纯核心，外界只经模型、工具集、会话记录三个接口进来。正式命令在这一阶段不向模型提供工具，可见行为与 P1 相同。替代方案：让循环直接依赖模型边界和注册表，被第 4 节的依赖方向禁止，守卫会拦；现在就把 read_file 挂到正式命令上，显示、会话记录和路径边界都还没有交付。回滚策略：删除三个新目录，Session.start_turn 回到只发一次请求，Provider 回到只取出回复文本；会话记录一直在内存里，磁盘上没有需要回滚的东西。
```

判定为重大的依据是 architecture.md 第 5 节的“新增 owner”与“改变协议边界”。这是第一次追加 Owner 章节，所以确认块守卫（技术债 CCD-002）排在本阶段最前面。确认块在 architecture.md 第 7 节和本计划各有一份，内容相同；仓库所有者于 2026-11-24 确认，两处已一起签署。

## 进度记录

每刀一条，按日期追加，不改写历史。

### 2026-11-24

- 改动：守卫先行。tests/integration/test_guard_architecture.py 检查两件事：src/lime_star 下每个包的导入不超出 architecture.md 第 4 节的依赖矩阵，模型客户端 SDK 只出现在 model_provider；第 7 节的每个 Owner 章节都带一份填写完整并已签署的确认块。依赖矩阵从架构图里读，架构图是唯一来源。verify-local 新增任务 architecture，由产品代码、架构图或守卫本身的改动触发，任务从 10 个变成 11 个。技术债 CCD-002、CCD-003 清退。
- 改动：protocol（项、回合结局，以及模型、工具集、会话记录三个接口）；agent_runtime 的 run_turn；tool_runtime 的 Registry、参数校验和 read_file；model_provider 的 respond 取代 complete；app 把三者装配起来，Record.messages 换成 Record.items；cli 显示步数上限的结局。architecture.md 的目录地图、第 4 节依赖矩阵和 Owner 章节 7.1；governance.md、scripts/README.md、根 README.md、本目录的 README.md。测试：tests/unit 下新增 38 条，tests/integration 下新增 40 条。
- 验证：逐项结果见验证矩阵，失败回写见验证合同。循环模块的导入只有 collections.abc 和 lime_star.protocol。
- 观察到但没有处理：
  1. 模拟的 Ctrl+C（_thread.interrupt_main）打不断一次长的阻塞，只在上一个字节码边界生效。入口用例里的测试工具因此按 0.1 秒的切片等待，取消在一个切片内生效。真实的 Ctrl+C 靠 CPython 的控制台事件唤醒主线程，P1 已在真实控制台里验证过。路线图 P4 的 run_command 等待命令结束时要用切片等待，否则测试里的取消要等到命令结束或超时才生效。
  2. 会话记录里可能留下没有结果的工具调用，有两种情况：取消时被中断的调用和它后面的调用；达到步数上限时最后一次响应里的调用。真实接口会拒绝带着它们的后续请求，因为 assistant 消息里的 tool_calls 后面必须紧跟 tool 消息。P2 的正式命令没有工具，到不了这里。P3 让工具进入正式命令之前必须定下怎么处理：给没有执行的调用补一条“没有执行”的结果，或者把它们从模型可见的历史里去掉。本阶段的用例不在这种记录之后继续对话，所以没有把这种请求形状固定下来。
  3. 被取消的请求在接口那边照常跑完并计费，P1 已记录；带工具调用的回合同样如此。
- 未验证：
  - Live：P2 不跑，见验证矩阵。所以真实接口上还有四件事没有对过：配置的模型是否接受我们的工具定义并返回工具调用；它是否返回推理内容，多轮工具调用是否要求回传；工具调用缺少编号的情况是否真的存在；正式命令的请求结构没变，这件事只对着替身验证过。
  - R12.5-S1（终止正在运行的命令）：命令执行属于 P4。
  - R12.6-S1 在带工具调用的回合上：取消之后会话还能继续，P1 的用例只在不带工具调用的回合上验证过；带工具调用的回合取决于上面第 2 条。
  - R13.14、R13.15（显示工具调用和结果摘要）：属于 P3，所以 P2 的正式命令不向模型提供工具。
  - Windows 以外的平台：只在 Windows 上验证。mypy 按 Linux 平台口径检查通过。
  - Python 3.11 到 3.13：没有安装，只在 3.14.5 上跑过。
  - CI：需要 push，仓库所有者尚未要求。
- 完成度：95%。Agent 侧的实现、本地验证、规则与文档同步已完成。剩下取决于仓库所有者：确认架构，按路线图 P2 的验收动作核对，然后说“提交”。
- 下一刀：仓库所有者确认架构后，把两处确认块签署，重跑 verify:local 确认 11 个任务通过。再请仓库所有者回答“待仓库所有者决定”里的两件事，它们决定 P3 的计划怎么写。

### 2026-11-24（架构确认与提交）

- 改动：仓库所有者回复“确认架构，并提交”。architecture.md 第 7 节和本计划的确认块都已签署，署名用“仓库所有者”，与需求确认时的写法一致。
- 验证：签署后 uv run pytest tests/integration/test_guard_architecture.py -q 是 21 条通过；npm run verify:local -- --full 在签署后的工作树上通过，11 个任务，其中 test:unit 是 195 条通过、2 条跳过（Live），test:guards 是 41 条，architecture 是 21 条。本条随本轮改动一并入库。
- 未跑：CI，需要 push，仓库所有者没有要求。
- 完成度：95%。还差 CI；路线图 P2 的阶段结论等 CI 通过后再追加。
- 下一刀：仓库所有者要求 push 之后核对 CI；通过后在路线图的进度记录里追加 P2 的阶段结论，把本计划标为 done，并从 README.md 的当前计划表移除。P3 开工前先请仓库所有者回答“待仓库所有者决定”里的两件事。

### 2026-11-25（CI 与收尾）

- 改动：提交 2cc4cbe 随 P3 的提交 23c431d 一起推送（f844e54..23c431d）。路线图里 P2 的阶段结论已于 2026-11-24 追加，其中写的“CI 没有跑”由下面这条结果补上。本计划标为 done，并从 README.md 的当前计划表移除。
- 验证：CI 运行 45515242850 针对 23c431d 通过，这个提交包含本计划的改动；verify 作业的 Local gate (full) 在 Linux runner 上成功。依据是运行、作业和步骤的状态，日志没有读。这是本阶段和 P3 的代码第一次在 Windows 以外运行。
- 未验证：Live 不在 P2 的证据等级里，没有跑。Python 3.11 到 3.13 仍然没有在本地跑过。
- 完成度：100%
- 下一刀：无。

## 当前结论

- 治理四分类：current 新增 protocol（项、回合结局、三个边界接口）、agent_runtime（run_turn）、tool_runtime（Registry、参数校验、read_file）、model_provider 的 respond、app 的装配（open_session 的 tools 参数，Session 经循环跑回合，Record.items）、cli 对步数上限的显示、两条架构守卫和 verify-local 的 architecture 任务、architecture.md 第 4 节的依赖矩阵与 Owner 章节 7.1。compat、deprecated、dead 均无新增或删除。删掉的只有 current 内部被直接替换的入口：Provider.complete，model_provider 导出的 Message、ModelError、Reply，Record.messages，以及 app 里 Outcome 与 TurnResult 的定义（两个名字挪进 protocol，app 照旧导出）。它们不是能力的退役，不属于四类中的任何一类。
- 验证结果与未验证原因：见验证矩阵与进度记录。架构确认块已由仓库所有者签署，本地门禁 11 个任务通过；提交随 P3 一起推送后 CI 通过（运行 45515242850）。路线图 P2 的五条退出条件逐条有结果：循环状态机的四种转移在不联网的单元测试里各有用例；工具结果不打断回合，循环按 R12.1 的顺序进行；注册表支持按名称注册与查找，工具有名称、描述、JSON Schema 参数和执行函数；read_file 可被注册，R5.1 到 R5.3 在入口集成里各有用例；循环模块只导入 collections.abc 和 lime_star.protocol。签署之前，本地门禁停在确认块守卫上，那是“未确认的重大变更不得标记完成”的机械表现。
- 来源声明：对照阅读了 lime 仓库 lime-rs/crates/agent-runtime/src/reply_loop.rs、同目录 provider_turn.rs 的文件头注释，以及 scripts/check-import-boundaries.mjs 与 scripts/governance/check-architecture-confirmation.mjs 的做法。只取三个思路：把“已经试了几次、还能不能继续”做成不依赖任何东西的纯状态；一步一物化，工具全部完成后才发下一次请求；守卫要能在违例上被证伪。按本仓库语境重写，没有复制原文。另读了 openai SDK 3.58.0 的类型声明，用来确定工具定义、工具调用参数和 omit 的写法。

完成度: 100%
