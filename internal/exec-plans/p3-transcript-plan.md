# p3-transcript 计划

状态: done
日期: 2026-11-24
主目标: 让每一次模型响应和每一次工具结果都落到同一份追加式的会话记录里，终端显示和测试只能从它派生；read_file 带着路径边界进入正式命令。

## 目标

每个会话在工作目录下有一份 JSON Lines 的会话记录，项按发生顺序逐项落盘，带着序号、时间和关联键；回合的开始和四种结局都在记录里。终端上看到的每一行都由这份记录投影得到。读回只凭文件。真实模型的响应录制一次成为仓库里的夹具，之后不联网就能用回放走完"模型请求工具、执行、回填、再请求、结束"。正式命令里模型可以读工作目录里的文件，越界的读取被拒绝。item 的 JSON Schema 作为第一条契约登记。

## 当前事实

- 仓库所有者于 2026-11-24 说“read_file提到p3，开始P3”。前半句是对 P2 计划里“待仓库所有者决定”第 2 件的答复：read_file 在 P3 进入正式命令，路径边界 R8.1 到 R8.3 随之提前，但只约束 read_file。第 1 件（取消的回合要不要让模型知道）没有答复，本计划保持现状，见下面“待仓库所有者决定”。开工前检索未决项（rg "^未决 OQ-" internal/prd），没有命中。
- P2 已于 2026-11-24 提交（2cc4cbe），没有推送，CI 没有跑。路线图 P2 的五条退出条件都有结果，架构确认块已签署。
- P2 留下的形态：会话记录是 app 内存里的项，不落盘；循环经 protocol 里的写入接口写项；取消或达到步数上限时，记录里会留下没有结果的工具调用（P2 计划“观察到但没有处理”第 2 条）。read_file 只在入口集成测试里经 open_session 的 tools 参数注册。
- 目录地图里 thread_store 与仓库根的 protocol/ 两项登记为“路线图 P3”；.lime-star 已有，里面是请求日志。
- 动手前核实的环境事实：httpx2 2.16.2 有 MockTransport 和响应事件钩子，回放与录制可以经 open_session 现有的 client 参数注入，产品代码不用加开关；Windows 上 _winapi.CreateJunction 不需要管理员权限就能建目录联接，Path.resolve() 会跟踪它；逐项追加并 flush 加 fsync 实测约 1 毫秒。
- lime 对照阅读（只读，仓库位置见 architecture.md）：internal/aiprompts/query-loop.md 的“固定主链”，以及 internal/aiprompts/state-history-telemetry.md 的“固定主链”和“持久会话与历史事实源”。取三个思路：回合的输入只快照一次，下游不得各自重组另一份真实输入；请求记录带上会话和回合的关联键才算事实源；持久历史只有一个读模型入口，界面和脚本不再各扫一遍拼出第二套。按本仓库语境重写，没有复制原文。

## 写集与避让

### 本轮认领写集

新建：

- protocol/thread-items.schema.json：会话记录一行的 JSON Schema。
- src/lime_star/thread_store/ 下的 __init__.py、transcript.py
- src/lime_star/tool_runtime/paths.py：工作目录边界。
- tests/unit/ 下的 test_transcript.py、test_paths.py、test_thread_items_schema.py
- tests/links.py：建目录链接的测试工具。
- tests/integration/ 下的 test_transcript.py（Gate A）、replay.py（回放传输与夹具读取）、test_fixture.py（Current fixture）、record_provider.py（录制）
- tests/fixtures/provider/read_file.json：从真实模型录制的一组请求与响应。
- 本计划

修改：

- src/lime_star/protocol/ 下的 items.py、turn.py、__init__.py：信封、回合开始、回合结局、批准三类项，项与 JSON 的互转，写入接口改名。
- src/lime_star/agent_runtime/loop.py：写回合开始与结局项；没有执行的调用补上结果。
- src/lime_star/tool_runtime/ 下的 registry.py、read_file.py、__init__.py：结果摘要、路径边界、正式命令的默认工具集。
- src/lime_star/model_provider/ 下的 provider.py、prompt.py：历史改为记录里的项；系统指令写明模型现在能读文件。
- src/lime_star/app/ 下的 session.py、__init__.py：会话记录改用 thread_store，读回只凭记录，显示回调。
- src/lime_star/cli/chat.py：显示改为记录的投影。
- scripts/check-file-size-governance.mjs：排除 .lime-star。它是共享热区里的根脚本，本轮没有其他 Agent 在工作，改动只有排除目录里的一个条目。
- 根 AGENTS.md：加入“不得自己拼第二份会话真相”的硬规则。
- internal/aiprompts/architecture.md（共享热区）：目录地图两行的状态，Owner 章节 7.2 与确认块。
- internal/aiprompts/governance.md：守卫表一行。internal/aiprompts/quality-workflow.md：业务主链那一行绑定 Current fixture 的命令。
- internal/roadmap/agent-practice.md：按仓库所有者的决定调整 P3、P4 的范围和验收动作；补 P2 的阶段结论。
- governance/contracts.json 与 contracts-state.json：登记第一条契约，状态文件由 --update 生成。
- scripts/README.md、根 README.md、本目录的 README.md。
- P2 的用例随接口调整：tests/unit/ 下的 test_loop.py、test_registry.py、test_read_file.py；tests/integration/ 下的 fake_model.py、support.py、test_turn.py、test_loop.py、test_tools.py、test_cli_chat.py、test_cli_process.py。test_cli_console.py 和 conftest.py 没有改。

### 只读避让写集

- ../prd/：需求已确认，不改。read_file 进入正式命令与路径边界的阶段调整写在路线图里。
- ../research/、../develop/、../tech/harness/README.md、../test/harness-evals.md：P3 只按它们的目标形状设计数据，状态仍由 P6 改。
- governance/ 下的另外两个基线：本轮不新增 scripts 目录，基线不变。
- scripts 下其余脚本，.github/workflows/quality.yml。

## 删除集

- app 的 Record 类型与 Record.items、Record.turns，以及 Session 内存里的项列表和回合结局列表：由 read_thread 直接返回记录里的项取代。
- protocol 里写入接口的名字 Transcript：改名 Journal，名字让给 thread_store 里真正的会话记录。
- cli/chat.py 的 _show：由投影函数取代。
- open_session 的 tools 留空时的空注册表：改为默认注册 read_file。
- 系统指令里“你现在只有对话能力”的说明。
- P2 用例里与“取消后不补写结果”绑定的断言：行为改了，用例随之改。
## 本阶段的默认选择

1. 会话记录的一行由信封和项组成：信封是序号、时间、会话标识（thread_id）、回合标识（turn_id）；项是类型和它的载荷。一个会话一个文件，位置是 .lime-star/threads/<thread_id>.jsonl（决策 D-23、D-29）。
2. 每项追加后 flush 并 fsync，然后才继续处理（R6.5）。实测每项约 1 毫秒。
3. 读回时，末尾没有换行的残行不算一项；看不懂的项类型直接报错，不悄悄丢掉。
4. app 不再在内存里保留第二份记录。每个回合开始时从文件读出之前的项；回合里新写的项由追加的返回值积累，不在回合中途重读文件。
5. 回合开始项和回合结局项由循环写。被 Ctrl+C 取消的回合当场写下结局；进程被强制结束而没收尾的回合，由读取的一方判为中断（R9.3，属于 P5）。
6. 没有执行的工具调用补一条出错的结果：取消时写"没有执行：用户取消了这个回合。"，达到步数上限时写"没有执行：回合已达到步数上限。"。理由：R7.13 把用户拒绝的操作也作为工具结果交给模型；这样记录里每次调用都有且只有一条结果，真实接口才接受后面的请求。落选的备选：把这些调用从模型可见的历史里去掉，那违反 R2.1 的"带上全部历史"。这改变了 P2 的做法（P2 不补写）。
7. 回合结局项不上线路，也就是不告诉模型那个回合被取消过。这是"取消的回合要不要让模型知道"的待定项，仓库所有者还没有答复，所以保持 P1 的现状。把项转成线路消息的只有模型边界的一处（_messages），之后怎么定都只改那一处。
8. 终端显示是记录的投影。app 在每一项落盘后把这一项交给显示回调，回调只看项、不另存状态，所以显示顺序就是记录顺序（R6.1-S1）。文案：模型文本原样输出；工具调用是"调用 <名称> <参数原文>"；结果是"结果：<摘要>"，出错时是"结果出错：<摘要>"；结局为取消时输出"已取消。"，为步数上限时输出"回合结束：<原因>。"，为出错时往标准错误写"回合出错：<原因>。"，完成时不另输出。
9. 工具的输出带一行摘要，随结果项记录，只用于显示；交给模型的只有结果的内容本身。R6.4 的比对对象是内容。
10. 路径边界：用 Path.resolve() 取真实位置（展开 ..、跟踪符号链接和目录联接），在 Windows 上用 os.path.normcase 之后比较。越界时返回"超出工作目录"的结果，不读写文件。
11. 正式命令打开会话时默认注册 read_file，系统指令相应改写：模型能读工作目录里的 UTF-8 文本文件，不能写文件，也不能执行命令。
12. 回放与录制只在测试里。二者都经 open_session 现有的 client 参数注入 httpx 的传输或钩子，产品代码没有回放开关（R11.6）。另有一条守卫用例：src/lime_star 里不出现回放相关的名字。
13. 夹具是自描述的：录制时间、模型名、工作目录里的文件、用户的消息、逐次的请求与响应。回放时照它重建同样的工作目录和消息。比对时系统指令不参与（只记下它的哈希供参考），其余请求内容与录制时逐项相等；系统指令以后还会改，改了不该逼着重新录制。
14. 不为了校验 JSON Schema 引入依赖。契约用例核对 schema 的类型枚举、每个分支的字段名与 protocol 的数据类一致。
15. 批准项只有类型和字段（调用编号、工具名、参数、决定），没有生产它的流程；审批属于 P4。

## 待仓库所有者决定

1. 取消的回合要不要让模型知道。P2 的计划里提过，仓库所有者这一次没有答复。现在的做法见默认选择第 7 条。它影响真实使用：取消一个回合之后再提问，模型可能先把被取消的那件事做了再回答（P1 实测过一次，多用了 37 秒）。

## 阶段与退出条件

### A 协议与会话记录

- 退出条件：会话记录的一行由信封（序号、时间、会话标识、回合标识）和项组成；八类项都能写进去并按类型读回，批准流程属于 P4，在存储层验证（R6.6-S1）；每项写入后落盘（R6.5）；只凭文件读回，顺序与内容同写入时一致（R6.7-S1）；末尾残缺的半行不算一项；schema 与 protocol 的数据类逐类一致，契约登记进 governance/contracts.json，npm run test:contracts 通过。

### B 循环写入完整记录

- 退出条件：循环写下回合开始项；四种结局都写回合结局项并注明原因（R12.7-S1）；没有执行的调用各有一条出错的结果，记录里每次调用都有且只有一条结果；单元测试不联网、不依赖模型客户端。

### C 工具

- 退出条件：工具输出带一行摘要并随结果项记录；路径边界按解析后的真实位置判断，Windows 上不区分大小写（R8.1-S1、R8.2-S1、R8.3-S1、R8.3-S2、R8.3-S3）；read_file 越界时返回"超出工作目录"的结果，文件没有被读取；正式命令打开会话时默认注册 read_file，系统指令与之一致。

### D 入口、投影与模型边界

- 退出条件：从 open_session 与 start_turn 驱动时，先记录再执行（R6.2-S1），结果回填后才请求（R6.3-S1、R6.3-S2）；请求日志的 thread_id 和 turn_id 能在会话记录里恰好找到对应的那一个回合（R3.4-S1）；read_thread 的结果与文件逐项一致（Gate A，也是硬规则的守卫）；会话记录里的工具参数和结果与发给模型的内容相同（R6.4-S1）；一个会话在磁盘上只有一份记录，项的顺序与终端上出现的顺序一致（R6.1-S1）；终端显示模型文本、每次工具调用的名称和目标、一行结果摘要（R13.14-S1、R13.14-S2、R13.15-S1）；进程被强制结束时记录里只有完整的行（R6.5-S1）。

### E 夹具

- 退出条件：录制模块从配置的真实模型录一组请求与响应，存进 tests/fixtures/provider/，夹具里没有密钥和本机绝对路径；默认运行的回放用例不联网，用录制的响应驱动 start_turn 走完"模型请求工具、执行、回填、再请求、结束"（R11.1-S1、R12.1），并注明模型为回放夹具；产品代码里没有回放开关（R11.6-S1）。

### F 规则、守卫与文档

- 退出条件：AGENTS.md 的硬规则与 governance.md 的守卫表同步；architecture.md 的目录地图与 Owner 章节 7.2 备好；行数门禁跳过 .lime-star；路线图按仓库所有者的决定更新；根 README 写明会话记录的位置和模型现在能读文件。

### G 收尾

- 退出条件：路线图 P3 的三条退出条件逐条有结果；交付的需求逐条有验证记录；ruff 与 mypy 通过；门禁有结果。

## 逐条验证

路线图 P3 交付的需求逐条对应到用例。没有写文件名的用例在 tests/integration/test_transcript.py 里；
写了 unit 的在 tests/unit 下。模型除注明外都是测试替身。

| 需求 | 场景 | 用例 | 证据等级 |
| --- | --- | --- | --- |
| R3.4 | R3.4-S1 | test_every_request_log_record_points_at_exactly_one_turn | 入口集成加 Gate A |
| R6.1 | R6.1-S1 | test_one_session_leaves_one_file_and_the_terminal_follows_it；test_cli_process.py 里的 test_a_tool_call_is_shown_in_a_real_process | Gate A 加入口集成；真实进程那条是 Gate B 回归 |
| R6.2 | R6.2-S1 | test_the_response_is_on_disk_before_its_tools_run；unit 的 test_loop.py 里的同名用例 | Gate A 加 Unit |
| R6.3 | R6.3-S1、R6.3-S2 | test_results_are_written_before_the_next_request；unit 的 test_loop.py 里的 test_every_tool_result_is_recorded_before_the_next_request | Gate A 加 Unit |
| R6.4 | R6.4-S1 | test_the_tool_arguments_and_results_recorded_are_what_the_model_receives | Gate A。用的是被截断的读取结果；被截断的命令输出属于 P4 |
| R6.5 | R6.5-S1 | test_a_killed_process_leaves_only_complete_lines；unit 的 test_transcript.py 里的 test_a_partial_last_line_is_not_an_item | Gate A（真实进程被强制结束）加 Unit |
| R6.6 | R6.6-S1 | test_a_cancelled_turn_records_its_end_on_the_spot；unit 的 test_transcript.py 里的 test_every_kind_round_trips | Gate A 加 Unit。批准项没有生产它的流程，只在存储层验证往返 |
| R6.7 | R6.7-S1 | test_what_read_thread_returns_is_what_the_file_holds；unit 的 test_transcript.py 里的 test_every_kind_round_trips | Gate A 加 Unit |
| R11.1 | R11.1-S1 | test_fixture.py 里的 test_the_recorded_read_file_exchange_drives_the_whole_chain | Current fixture，模型为回放夹具 |
| R11.6 | R11.6-S1 | test_fixture.py 里的 test_the_product_has_no_replay_switch | 守卫 |
| R12.1 | R12.1-S1 | 同 R11.1-S1 的回放用例；test_loop.py 里的 test_a_tool_call_is_run_and_its_result_goes_back_to_the_model | Current fixture 加入口集成 |
| R12.7 | R12.7-S1 | test_a_cancelled_turn_records_its_end_on_the_spot、test_each_ending_is_written_with_its_reason；unit 的 test_loop.py 里四种结局各一条 | Gate A 加 Unit |
| R13.14 | R13.14-S1、R13.14-S2 | test_cli_chat.py 里的 test_a_tool_call_and_its_result_are_shown_as_they_are_recorded；test_cli_process.py 里的 test_a_tool_call_is_shown_in_a_real_process | 入口集成；真实进程那条是 Gate B 回归 |
| R13.15 | R13.15-S1 | 同上，另加 test_cli_chat.py 里的 test_a_failed_tool_result_is_shown_with_its_error | 入口集成加 Gate B 回归 |
| R8.1 | R8.1-S1 | unit 的 test_paths.py 里的 test_a_path_inside_the_workdir_is_allowed | Unit |
| R8.2 | R8.2-S1，read_file | unit 的 test_read_file.py 里的 test_a_path_outside_the_workdir_is_refused_without_reading；test_tools.py 里的 test_a_file_outside_the_workdir_is_refused | Unit 加入口集成 |
| R8.3 | R8.3-S1 | unit 的 test_paths.py 里的 test_a_link_to_outside_cannot_be_followed；test_read_file.py 里的 test_a_link_to_outside_is_refused | Unit。Windows 上用的是目录联接，符号链接那一支没有跑过 |
| R8.3 | R8.3-S2 | unit 的 test_paths.py 里的 test_dots_that_come_back_are_allowed；test_read_file.py 里的 test_a_path_that_wanders_out_and_back_is_allowed | Unit |
| R8.3 | R8.3-S3 | unit 的 test_paths.py 里的 test_directories_spelled_with_another_case_are_the_same；test_read_file.py 里的 test_another_case_spelling_reads_the_same_file | Unit，只在 Windows 上运行 |

硬规则的守卫是表里 R6.7 的第一条：read_thread 的结果与文件逐项一致。

## 验证矩阵

| 阶段 | 命令 | 证据等级 | 结果 |
| --- | --- | --- | --- |
| A | uv run pytest tests/unit/test_transcript.py tests/unit/test_thread_items_schema.py -q | Unit | 通过：22 条加 13 条 |
| A | npm run test:contracts | 契约 | 通过：契约 1 项（thread-items），哈希已登记 |
| B | uv run pytest tests/unit/test_loop.py -q | Unit（不联网） | 通过：12 条 |
| C | uv run pytest tests/unit/test_paths.py tests/unit/test_read_file.py tests/unit/test_registry.py -q | Unit | 通过：8 条、15 条、18 条 |
| D | uv run pytest tests/integration/test_transcript.py -q | Gate A 加入口集成（模型为测试替身） | 通过：9 条，其中一条驱动真实进程并把它强制结束，之后没有残留的会话进程 |
| D | uv run pytest tests/integration/test_turn.py tests/integration/test_loop.py tests/integration/test_tools.py tests/integration/test_cli_chat.py -q | 入口集成（模型为测试替身） | 通过：12 条、12 条、7 条、15 条 |
| D | uv run pytest tests/integration/test_cli_process.py tests/integration/test_cli_console.py -q | Gate B 回归（真实进程，模型为测试替身；控制台用例含真实 Ctrl+C 事件） | 通过：18 条、5 条 |
| E | uv run python -m tests.integration.record_provider | Live（录制） | 通过：北京时间 2026-11-24 23:03，用仓库所有者配置的真实模型 glm-5.2 录成 read_file.json，两组请求与响应，结局为完成，交回模型的工具结果是真的读到了三行。第一次录制（23:01）录到的是失败路径，原因是录制模块忘了往工作目录放文件；修掉后重录，前一份被覆盖 |
| E | uv run pytest tests/integration/test_fixture.py -q，运行前禁用全部 socket | Current fixture（模型为回放夹具） | 通过：2 条，0.25 秒。回放时发给模型的内容与录制时逐项相同，系统指令除外 |
| 全程 | uv run pytest tests/unit -q，运行前禁用全部 socket | Unit | 通过：139 条，1.9 秒 |
| 全程 | uv run pytest -q | 汇总 | 签署后 260 条通过，2 条跳过（Live）。签署之前另有 1 条失败，就是 7.2 的确认块守卫，见进度记录 2026-11-24 |
| 全程 | uv run ruff check . 与 uv run ruff format --check . | 静态检查 | 通过：100 个文件 |
| 全程 | uv run mypy，另按 Linux 平台口径跑一次 | 类型检查 | 通过：58 个文件 |
| 全程 | 密钥守卫的 8 条规则，对本轮新增和修改的 48 个文件另扫一遍；夹具另查授权头、密钥变量名、接口主机名和主目录路径 | 守卫 | 通过：0 处命中。正式的密钥守卫只扫已跟踪的文件，本轮的新文件要等提交后才在它的范围内 |
| F | node scripts/check-contracts.mjs、check-doc-links.mjs、check-file-size-governance.mjs | 守卫 | 通过。行数门禁现在跳过 .lime-star。改 schema 会选中 contracts 任务，改 thread_store 会选中 architecture 任务（dry-run 核对过） |
| G | npm run verify:local -- --full | 门禁 | 通过：签署后的工作树上 11 个任务全部通过，test:unit 里 260 条通过、2 条跳过（Live），test:guards 41 条，architecture 21 条。签署之前它停在 test:unit 的 7.2 确认块守卫上：前 8 个任务通过，那一轮是 259 条通过、1 条失败；fail-fast 之后 test:guards 和 architecture 没有执行，单独跑各自是 40 条通过加这 1 条失败、20 条通过加这 1 条失败。见进度记录 2026-11-24 |

## 验证合同

预算标签: budget:normal（定向测试加门禁）

主链: app 回合入口 start_turn -> agent_runtime 回合循环 -> model_provider 的一次请求 / tool_runtime 的一次工具执行 -> thread_store 的会话记录 -> CLI 投影

Happy Path:

1. 配置齐全，不带参数运行 lime-star，在工作目录开始会话。会话记录的文件在第一项写入时出现在 .lime-star/threads 下。
2. 用户请它读一个文件。循环写下回合开始项和用户消息项，每写一项都落盘，终端的显示来自这些项。
3. 模型请求 read_file。循环先写下这次响应的项，再执行工具；路径落在工作目录内，结果写进记录。
4. 循环发起下一次请求，历史是从记录读出的项。模型给出最终回复，写进记录，终端显示它。
5. 循环写下回合结局项。用户在磁盘上打开这份记录，看到的顺序与终端一致。

Evidence Layers:

- 必须达到: Current fixture（录制的真实响应驱动完整主链）加 Gate A（读文件核对会话记录的内容）。
- 禁止替代: 用真实模型的单次成功对话代替夹具驱动的完整主链测试；只核对 read_thread 的返回值而不读文件；回放夹具冒充真实模型。

必跑命令:

| 命令 | 目的 | 状态 |
| --- | --- | --- |
| uv run pytest tests/unit -q | 循环、会话记录、路径边界、schema 的纯逻辑，不联网 | 通过：139 条，运行前禁用全部 socket |
| uv run pytest tests/integration/test_transcript.py -q | Gate A：会话记录的事实 | 通过：9 条 |
| uv run pytest tests/integration/test_fixture.py -q | Current fixture：回放驱动完整主链 | 通过：2 条，禁用 socket 后通过 |
| uv run pytest tests/integration/test_turn.py tests/integration/test_loop.py tests/integration/test_tools.py tests/integration/test_cli_chat.py -q | 入口集成 | 通过：46 条 |
| uv run pytest tests/integration/test_cli_process.py tests/integration/test_cli_console.py -q | 主链回归 | 通过：23 条 |
| npm run test:contracts | 契约检查 | 通过：契约 1 项 |
| uv run ruff check . 与 uv run ruff format --check . | 静态检查 | 通过 |
| uv run mypy | 类型检查 | 通过 |
| npm run verify:local -- --full | 本地门禁 | 通过：签署后的工作树上 11 个任务 |

失败回写: 测试失败时三选一，修产品、修测试、补守卫。本轮的记录：

- 修产品。写入接口 Journal 起先写成带方法的 Protocol，函数传不进去（mypy 不认），改成可调用的类型别名；thread_store 的 append 和 app 里的闭包都满足它。
- 修产品。Transcript.append 数序号时把整个文件解码了一遍，改成数换行；并且文件末尾是半行时拒绝接着写，否则新的一项会和那半行连在一起。
- 修产品。Journal 定型之前，protocol 里少了 Clock 和 NewId 的导入，mypy 报出后才补齐。
- 修测试，产品行为没有为这些失败改动。P1 的进程用例是“看到回复就发下一行”，撞上了回复显示到回合返回之间的窗口（见“观察到但没有处理”第 1 条），改成等输入提示。Gate A 用例里有三处期望写错：取消的回合没有 model_text；强制结束那条的第一个回合有两次调用；R6.4 那条把请求数错了。循环的单元用例有两处下标写错。
- 修测试夹具。录制模块忘了往工作目录放文件，第一次录到的是失败路径；补上后重录。替身模型加了 on_request 钩子，用例才能看到请求到达那一刻磁盘上的状态。
- 修测试。tests/links.py 的平台判断从 os.name 改成 sys.platform，mypy 按 Linux 口径检查时才认。
- ruff 报出的行宽问题按修产品和修测试处理：中文按两列计宽。

完成标准:

- [x] 必跑命令全部有结果记录
- [x] 证据等级达到 Evidence Layers 要求：Current fixture 与 Gate A 都已达到
- [x] 下一刀已写明

## 架构确认

```text
Architecture impact: major
架构图已更新：architecture.md 第 2 节目录地图（thread_store、protocol 两行的状态列）、本节 7.2
Responsible developer confirmation: 仓库所有者，2026-11-25
确认内容：本阶段新增 thread_store 和契约目录两个 owner，第一次把会话记录持久化到磁盘，并让终端显示只从它派生。正式命令第一次向模型提供工具：read_file，带工作目录边界。替代方案：让显示直接吃循环发出的事件而不落盘，那样显示会成为第二份会话真相，回放和证据也无从派生；把回放做成产品命令的开关，被 R11.6 禁止，所以回放只经测试注入的 HTTP 传输。回滚策略：删除 thread_store 和仓库根的 protocol 目录，取消契约登记；Session 回到 P2 的内存记录，cli 回到按回合结局显示；默认工具集回到空。已经在工作目录 .lime-star/threads 下写出的记录文件不需要迁移，回滚后没有代码读它们。
```

判定为重大的依据是 architecture.md 第 5 节的“新增 owner”与“引入新的持久化”。确认块在 architecture.md 第 7 节和本计划各有一份，内容相同；仓库所有者于 2026-11-25 确认，两处已一起签署。

## 进度记录

每刀一条，按日期追加，不改写历史。

### 2026-11-24

- 改动：会话记录。thread_store 的 Transcript 把每一项追加进 .lime-star/threads/<thread_id>.jsonl 并落盘，只凭文件读回；protocol 加了信封 Entry 和回合开始、回合结局、批准三类项，写入接口定名为 Journal。循环写下回合的开始与结局，给没有执行的调用补一条出错的结果。app 不再在内存里留第二份记录，read_thread 只凭文件，每一项落盘后交给显示回调。cli 的显示改成记录的投影。
- 改动：契约。仓库根的 protocol/thread-items.schema.json 作为第一条契约登记（thread-items）；契约用例核对它与数据类一致。
- 改动：工具。read_file 接上工作目录边界，输出带一行摘要；正式命令默认注册 read_file，系统指令相应改写。
- 改动：夹具。tests/integration/record_provider.py 从真实模型录制，replay.py 在测试里回放，tests/fixtures/provider/read_file.json 是录下来的那一组。
- 改动：规则与文档。AGENTS.md 加入“不得自己拼第二份会话真相”的硬规则；architecture.md 的目录地图与 Owner 章节 7.2；governance.md、quality-workflow.md、scripts/README.md、根 README.md、本目录的 README.md；行数门禁跳过 .lime-star。路线图按仓库所有者的决定调整了 P3、P4 的范围，并补了 P2 的阶段结论。
- 验证：逐项结果见验证矩阵，需求与用例的对应见“逐条验证”，失败回写见验证合同。
- 真实接口上看到的事实（来自录制）：
  1. 真实响应带 reasoning_content，工具调用那一条的 content 是空串。我们不回传推理内容，第二次请求照样返回 200 和连贯的回答。
  2. tool_calls 的每一项多一个 index 字段，最终回复的 tool_calls 是 null，两种形状都接得住。
  3. 配置的模型接受了我们的工具定义，用相对路径 notes.txt 调用了 read_file。
  4. 读不到文件时，模型没有猜，而是请用户确认路径。这是 R14.4 要求的行为，是第一次录制的意外收获。
- 观察到但没有处理：
  1. 回复在写进记录时就显示。从回复出现到回合返回之间（约 1 毫秒，是写结局项的 fsync）到达的输入，按 R13.8 被当作回合中的输入丢弃。人打不了这么快，自动化脚本会撞上：同步点必须是输入提示，不是回复文本。P4 的冒烟脚本要照此写。没有改成“回合返回后再显示最终回复”，因为 R13.14-S2 要求文本产出后就显示。
  2. Ctrl+C 恰好落在工具返回之后、结果写进记录之前（微秒级的窗口）时，那次调用会没有结果；补写“没有执行”的那几毫秒里再来一次 Ctrl+C，回合结局项会写不上。前者 P4 的 write_file 和 run_command 要专门设计，那两个工具执行了却没有结果是要紧的事；后者由读取的一方在 P5 判为中断。
  3. 模拟的 Ctrl+C 打不断一次长的阻塞（P2 已记录）。P4 的 run_command 等待命令结束时要用切片等待。
  4. 每次追加都要把文件读一遍来数行。MVP 的会话只有几百项，开销可以忽略；会话很长时再考虑。
  5. Windows 上 lime-star 命令是一个启动器，会话进程是它的子进程。要真正强制结束会话，得结束整棵进程树，测试里的 kill_tree 用的是 taskkill /T。P4 的冒烟脚本收尾时要注意这一点。
  6. 第一次录制录到的“文件不存在”的应对是一份很好的真实失败样本，但被重录覆盖了。P6 做失败样本时可以照这个办法再录。
  7. 仓库根的 .lime-star/ 里有以前 Live 测试留下的请求日志，本轮没有动它。
- 未验证：
  - Live 只做了录制，共 4 次真实请求（第一次 2 次，重录 2 次）。没有用真实模型跑完整的命令行会话，终端上真实模型的工具调用显示只有替身模型的证据。验收动作 1 要仓库所有者亲手做。
  - 只录了一轮工具调用。配置的模型在更长的工具调用里是否要求回传推理内容，没有验证。
  - 符号链接那一支：Windows 上用的是目录联接，符号链接需要管理员权限，没有跑。Windows 以外的平台没有跑，mypy 按 Linux 口径检查通过。
  - Python 3.11 到 3.13：没有安装，只在 3.14.5 上跑过。
  - CI：P2 的提交还没有推送，本轮的改动还没有提交。
  - 批准项：只有类型和往返，没有生产它的流程（P4）。
  - 恢复：有开始、没有结局的回合怎样恢复（P5）。
  - R6.4-S1 的字面场景是被截断的命令输出，这里用的是被截断的读取结果；命令输出属于 P4。
- 完成度：95%。Agent 侧的实现、验证、规则与文档同步已完成。剩下取决于仓库所有者：确认架构，按路线图 P3 的验收动作核对，然后说“提交”。
- 下一刀：仓库所有者确认架构后，把两处确认块签署，重跑 verify:local 确认 11 个任务通过；核对验收动作；说“提交”。“待仓库所有者决定”里那一件（取消的回合要不要让模型知道）仍待答复。

### 2026-11-25（架构确认与提交）

- 改动：仓库所有者回复“确认提交 and push”。architecture.md 第 7 节 7.2 和本计划的确认块都已签署，署名用“仓库所有者”，与需求确认时的写法一致。
- 验证：签署后 uv run pytest tests/integration/test_guard_architecture.py -q 是 21 条通过；npm run verify:local -- --full 在签署后的工作树上通过，11 个任务，其中 test:unit 是 260 条通过、2 条跳过（Live），test:guards 是 41 条，architecture 是 21 条。本条随本轮改动一并入库。
- 未跑：CI，它只能在推送之后跑。P2 的提交 2cc4cbe 和本轮的提交会一起推送。
- 完成度：95%。还差 CI；路线图 P3 的阶段结论等 CI 通过后再追加，P2 的计划也等同一次 CI。
- 下一刀：核对 CI；通过后在路线图的进度记录里追加 P3 的阶段结论，把本计划和 P2 的计划标为 done，并从 README.md 的当前计划表移除。“待仓库所有者决定”里那一件仍待答复，最好在 P4 开工之前定。

### 2026-11-25（CI 与收尾）

- 改动：路线图追加 P3 的阶段结论，本计划标为 done，并从 README.md 的当前计划表移除。
- 验证：推送后 CI 运行 45515242850 针对 23c431d 通过，verify 作业每一步成功。依据是运行、作业和步骤的状态，日志没有读，runner 上的 Python 版本不确定。Windows 以外的平台由此有了 CI 这一级的证据：目录链接那一支在 Linux 上走的是符号链接。
- 未验证：进度记录 2026-11-24 里列的未验证项，除了平台这一条，其余仍然成立：真实模型的完整命令行会话、更长的工具调用、Python 3.11 到 3.13、批准项的生产流程（P4）、恢复（P5）。
- 完成度：100%
- 下一刀：按路线图 P4 的开工话术开始 P4。开工前最好先定“取消的回合要不要让模型知道”，上面的“待仓库所有者决定”里提过，仓库所有者还没有答复。

## 当前结论

- 治理四分类：current 新增 thread_store（Transcript、encode、decode、read）；protocol 的信封 Entry、回合开始、回合结局、批准三类项和写入接口 Journal；契约 thread-items 与仓库根的 protocol 目录；工具边界的工作目录边界、结果摘要和默认工具集；测试里的录制与回放。current 扩展：循环写回合的开始与结局并给没有执行的调用补结果；read_file 接上路径边界；app 经 thread_store 持有会话记录并提供显示回调；cli 的显示改为记录的投影；模型边界的历史改为记录里的项；系统指令写明模型能读文件。compat、deprecated、dead 均无新增或删除。直接替换掉的内部入口不属于四类：app 的 Record 和内存里的项列表，protocol 里写入接口的旧名 Transcript，cli 的 _show，open_session 留空时的空注册表。
- 验证结果与未验证原因：见验证矩阵与进度记录。路线图 P3 的三条退出条件逐条有结果：交付的需求逐条有验证记录，其中先记录再执行、结果回填后才请求、只凭记录读回各有用例；录制的模型响应夹具驱动 start_turn 走完了完整主链；第一条契约已登记并通过契约检查。架构确认块已由仓库所有者签署，本地门禁 11 个任务通过；推送后 CI 通过（运行 45515242850）。
签署之前本地门禁停在 7.2 的确认块守卫上，那是“未确认的重大变更不得标记完成”的机械表现。
- 来源声明：对照阅读了 lime 仓库 internal/aiprompts/query-loop.md 的“固定主链”，以及 internal/aiprompts/state-history-telemetry.md 的“固定主链”和“持久会话与历史事实源”。只取三个思路：回合的输入只快照一次，下游不得各自重组另一份真实输入；请求记录带上会话和回合的关联键才算事实源；持久历史只有一个读模型入口。按本仓库语境重写，没有复制原文。另读了 openai SDK 与 httpx2 的类型声明，用来确定回放传输和响应钩子的写法。真实模型只用于录制夹具。

完成度: 100%
