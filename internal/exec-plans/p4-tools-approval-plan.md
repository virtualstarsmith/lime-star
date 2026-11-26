# p4-tools-approval 计划

状态: in_progress
日期: 2026-11-25
主目标: 补齐列目录、写文件和执行命令，危险操作必须经用户批准，并用 MVP 主场景证明 MVP 成立（Gate B）。

## 目标

开发者在空目录里启动 `lime-star`，让它新建一个脚本、运行它、报告结果：每一步写文件和执行命令都先在终端出现批准提示，用户输入 y 才执行，输入 n 则不执行，会话记录里留下批准项，模型的最终回复不把被拒绝的事说成已完成。列目录和读文件不需要批准。工作目录之外的写入不进入批准提示，直接作为工具结果交回模型。命令运行中按 Ctrl+C，命令连同它的子进程一起结束，已产生的输出如实记进会话记录。这一整套在一个真实的 lime-star 进程里由冒烟脚本自动跑通，核对的是会话记录和磁盘，不只是终端。

## 当前事实

- 仓库所有者于 2026-11-25 说“开始P4”。开工前检索未决项（`rg "^未决 OQ-" internal/prd`），没有命中。
- 工作树干净，HEAD 是 e9fb879。基线：`uv run pytest -q` 是 260 条通过、2 条跳过（Live），约 98 秒。
- P3 留下的形态：循环只依赖 protocol，经 `ToolSet`（specs、execute）调用工具边界；`Registry.execute` 总是给出一条结果；批准项 `Approval` 已有类型和字段（调用编号、工具名、参数、决定），但没有生产它的流程；app 的 `Session.start_turn(text, show=...)` 在调用线程上同步跑完一个回合；CLI 的显示是会话记录的投影；路径边界 `tool_runtime/paths.py` 的 `inside` 已经按真实位置判断。
- 路线图 P3 的“下一刀”带过来三件事，本计划都要处理：
  1. “取消的回合要不要让模型知道”仓库所有者还没有答复。本计划保持现状（回合结局项不上线路），见下面“待仓库所有者决定”第 1 条。
  2. 自动化脚本以输入提示为同步点，不是回复文本：冒烟脚本照此写，批准提示另有一个同步点。
  3. 模拟的 Ctrl+C 打不断一次长的阻塞：run_command 按切片等待。
- P3 计划“观察到但没有处理”第 2、5 条与本阶段直接相关：工具执行了却没有结果是要紧的事（write_file、run_command 要专门设计）；Windows 上 lime-star 是启动器，会话进程是它的子进程，收尾要结束整棵进程树。
- 动手前在本机核实的事实（临时脚本，仓库外）：系统是 Windows PowerShell 5.1（没有 pwsh），系统代码页是 65001，ACP 也是 65001；`powershell -Command "cmd /c exit 3"` 的进程退出码是 1 而不是 3，所以要追加一段语句把原生命令的退出码带出来；`-EncodedCommand` 会让标准错误变成 CLIXML，`-Command` 把命令当成一个参数则是纯文本，引号、`$`、多行、中文都传得对；作业对象一次 `TerminateJobObject` 能结束命令进程和它的子进程；PowerShell 每次启动约 0.46 秒。
- lime 对照阅读（只读，仓库位置见 architecture.md）：internal/aiprompts/query-loop.md 的“代码入口地图”和“current / compat / deprecated”（action/respond 是主链上一个可以恢复的入口，恢复路径只能复用当前回合的上下文，不得旁路拼第二份）；lime-rs/crates/tool-runtime 的目录结构（工具定义、执行决定、审批回应、进程取消、路径守卫在同一个 owner）。取三个思路，按本仓库语境重写，没有复制原文：
  1. 批准是主链上的一个节点，回应它经 app 回合入口的 `respond_action`，接着跑同一个回合、同一份会话记录，不另拼上下文。
  2. “要不要批准”由工具边界在执行前按工具判定，判定和执行在同一个 owner。
  3. 取消时先结束进程树，再把截至那一刻的输出作为结果写下来，不丢掉。

## 写集与避让

### 本轮认领写集

新建：

- src/lime_star/tool_runtime/ 下的 list_dir.py、write_file.py、run_command.py、tree.py
- scripts/smoke/agent_gate_b.py：Gate B 冒烟脚本。新增 scripts 一级目录 smoke，理由：路线图 P4 约定冒烟脚本放这里，与治理脚本分开；基线用 `node scripts/check-scripts-baseline.mjs --update` 登记。
- tests/unit/ 下的 test_list_dir.py、test_write_file.py
- tests/integration/ 下的 test_approval.py、test_run_command.py
- tests/fixtures/provider/mvp.json：从真实模型录制的 MVP 场景，三个回合。
- 本计划

修改：

- src/lime_star/protocol/ 下的 items.py、__init__.py：决定、等待批准的操作、批准来源、工具被中断时带出的结果；批准项的说明。
- src/lime_star/agent_runtime/loop.py：工具执行到一半被 Ctrl+C 打断时，如实记下它截至那一刻的结果。
- src/lime_star/tool_runtime/ 下的 registry.py、__init__.py：危险等级、执行前的批准、默认工具集。
- src/lime_star/app/ 下的 session.py、__init__.py：提问回调、respond_action、一个回合里等待批准的位置。
- src/lime_star/cli/chat.py：批准提示、读一行、把决定交回 app；批准项的投影。
- src/lime_star/model_provider/ 下的 prompt.py、provider.py：系统指令写明四个工具和审批；provider.py 只改一处说明，行为不变。
- protocol/thread-items.schema.json：批准项的说明（形状不变），重新登记契约。
- scripts/verify-local.mjs（共享热区里的根脚本）：任务表加 smoke:gate-b。本轮没有其他 Agent 在工作，改动只有任务表的一项。
- governance/ 下的 scripts-baseline.json、contracts-state.json：由各自的 `--update` 生成。
- 根 AGENTS.md（共享热区）：加入审批硬规则。
- internal/aiprompts/architecture.md（共享热区）：第 3 节加一条固定判断，7.1 的指引改指 7.3，追加 Owner 章节 7.3 与确认块。
- internal/aiprompts/governance.md：守卫表一行。internal/aiprompts/quality-workflow.md：业务主链一行绑定冒烟命令。
- tests/integration/ 下的 support.py（收尾结束整棵进程树；长睡命令的脚本；判断进程是否还活着）、replay.py、record_provider.py、test_fixture.py、test_tools.py、test_loop.py、test_cli_chat.py、test_cli_process.py、test_cli_console.py；tests/unit/ 下的 test_registry.py、test_loop.py。
- tests/fixtures/provider/read_file.json：按新的夹具形状重排，录下的数据不变。
- scripts/README.md、根 README.md、本目录的 README.md。
- internal/exec-plans/tech-debt-tracker.md：登记 CCD-005。

### 只读避让写集

- ../prd/：需求已确认，不改。与它有关的一处张力写在下面“待仓库所有者决定”。
- ../roadmap/agent-practice.md：路线图是只读避让集。阶段结论等仓库所有者验收、CI 通过之后再追加。
- governance/ 下的 file-size-baseline.json、contracts.json：本轮不改。
- scripts 下其余脚本，.github/workflows/quality.yml：它跑 verify:local 的全量，新任务自动进入。
- ../develop/、../research/、../tech/：只按它们的方法做验收，不改。

## 删除集

- 系统指令里“你现在不能写文件，也不能执行命令”的说明：由四个工具和审批的说明取代。
- 夹具旧的形状（顶层的 message 与 exchanges）：由 turns 取代。read_file.json 只重排，录下的请求与响应不变。
- `open_session` 的 tools 参数从协议类型 ToolSet 收窄为 Registry：app 每个回合要给它绑定批准来源，测试传入的也都是 Registry。没有文件被删除。

## 本阶段的默认选择

1. 危险等级按工具固定（决策 D-19）。`Tool` 多一个可选的 `danger`：只有危险工具有，它先检查这次调用，再给出向用户说明的内容（批准提示显示它）；检查发现问题（目标越界、父目录不存在、参数指向目录）时直接给出结果，不进入批准提示（R8.2-S2、R7.2-S1）。
2. 批准在工具边界里是结构性的：注册表执行危险工具时，先经批准来源取得批准，拿不到就不调用它的执行函数，直接给出“用户拒绝了这次操作，没有执行。”的结果（R7.6、R7.10、R7.13）。危险工具的执行函数只有一条路可以到达，不靠每个工具自觉。
3. 批准的流程归 app 回合入口。`start_turn(text, show=..., ask=...)` 每个回合有一个等待批准的位置；CLI 的 ask 显示说明、读一行，再用 `respond_action(call_id, decision)` 交回决定；app 拿到决定后先把批准项写进会话记录并落盘，再把决定交给工具边界。所以记录里的顺序固定是：工具调用、批准、工具结果（R7.12）。没有给 ask 时一律拒绝。
4. 等待中的批准只在内存里，不落盘。进程在等待批准时被结束，记录里只有调用项，没有批准项和结果项；P5 的读取方把这个回合判为中断（R9.3-S2），恢复后不重新请求它（D-24）。批准项的形状沿用 P3 定下的：一次批准请求对应一项，带工具名、参数、决定和时间。
5. 只有 y 算批准（R7.9，决策 D-20）：去掉首尾空白后恰好是 y；n、空输入、别的文字、输入结束、标准输入读不下去，都算拒绝。批准提示出现之前已经排队的输入不算回应：显示提示之前先把它们丢掉，计入“已忽略 N 行回合中收到的输入”（R13.8）。想批准，必须在看到提示之后输入。冒烟脚本因此以 `[y/n]` 为同步点。
6. 批准提示的标记用 ASCII：说明之后输出 `[y/n] `，不给换行，读用户的输入。决定落盘后由投影显示“已批准。”或“已拒绝。”，所以管道里的输出是 `[y/n] 已批准。`。写文件的说明里有目标路径、新建还是覆盖、全部内容和行数；执行命令的说明里是原样的命令（R7.7、R7.8）。
7. 批准项不上线路，和回合结局项一样。模型知道用户拒绝，是因为工具结果里有那句拒绝；不需要再给模型一份决定。
8. 命令执行到一半被 Ctrl+C 打断时，结果如实记录：run_command 先结束整棵进程树，再带上截至那一刻已有的输出，以“用户按 Ctrl+C 取消了回合，命令已被终止”开头；循环把它作为这次调用的结果写下，后面的调用各有一条“没有执行”，回合以取消结束（R12.5-S1）。循环靠 protocol 里的 `Halted` 认出这种中断，它带着那段结果。
9. write_file 写临时文件再替换目标文件。被打断或写失败时目标文件保持原样，临时文件被清掉，这时循环补写的“没有执行”属实。内容按 UTF-8 写成字节，不做换行符转换（R7.1-S2）。
10. run_command 在 Windows 上用系统自带的 Windows PowerShell（powershell.exe，-NoProfile、-NonInteractive、-Command），不找 PowerShell 7：它一定在，行为可预期。命令后面追加一段语句把退出码如实带出：最后一条语句成功是 0；失败时是最后一个原生命令的退出码，没有就是 1；命令自己写了 exit 就用它的。其他平台用 /bin/sh -c。
11. 命令的进程被圈起来：Windows 上放进一个作业对象（关闭句柄就结束全部进程，子进程自动入内），并带上 CREATE_NO_WINDOW；其他平台上启动时自成一个进程组。超时和取消都是结束整棵树，命令结束后它留下的后台进程也一并结束，所以没有命令能活过这个工具。圈不住时命令不执行。命令的标准输入是空设备：不让它读走用户的输入。
12. 命令结果的格式：第一行是退出码或终止的原因；之后是标准输出；标准错误非空时在后面加一行“（以下是标准错误）”。换行统一成 LF；先按 UTF-8 解码，解不开按系统代码页解码，解不开的字符用替换字符。超过 10000 个字符时只保留最后 10000 个，前面一行写明总共多少、截掉多少（R7.5，决策 D-18）。超时固定 120 秒（决策 D-17），测试经构造参数注入。
13. 终端摘要按决策 D-08 只占一行：run_command 是“退出码 N”，命令输出不回显到终端，它在会话记录里，模型的最终回复会转述。与主场景第 4 步的张力见“待仓库所有者决定”第 2 条。
14. list_dir 每行一项，“目录”或“文件”加名称；目录名大小写不同的排在一起（先按不区分大小写的名称排序）。不隐藏任何条目，包括点开头的和 .lime-star（决策 D-14）。路径为空时列出工作目录。
15. 正式命令的默认工具集是 read_file、list_dir、write_file、run_command，read_file 仍在第一位（P3 的回放夹具核对了它）。系统指令写明四个工具、哪些要批准、被拒绝和越界时怎么理解。
16. 回放夹具改成多回合的形状：一份夹具有工作目录里的文件和若干回合，每个回合有消息、批准的决定和逐次的请求与响应。录制脚本改成按场景录制。新增 mvp.json，三个回合：主场景（两次批准）、拒绝写文件、运行一条以退出码 1 结束的命令；后两个回合用来验证 R14.1-S1 和 R14.2-S1 的行为。
17. 冒烟脚本默认回放录制的夹具：本地起一个 HTTP 服务按序返回录下的响应，驱动一个真实的 lime-star 进程，模型标注为“回放夹具”；加 `--live` 时用真实模型。断言来自会话记录（用 thread_store 的读入函数读）和磁盘，终端输出只用来核对批准提示。回放时逐项比对发给模型的消息与录制时是否相同，这一项只在录制它的平台（Windows）上做，其他平台只核对角色的序列。
## 待仓库所有者决定

1. 取消的回合要不要让模型知道。P2、P3 的计划里都提过，还没有答复。本计划保持现状：回合结局项不上线路。P4 之后它多了一层事实：命令被 Ctrl+C 打断时，记录里有那条“命令已被终止，截至那一刻已有的输出”的工具结果，模型在下一次请求里看得到它，但看不到“这个回合被取消过”。建议到 P5 做恢复时一起定，因为恢复后的提示（R9.4）和它是同一件事的两面。
2. 主场景第 4 步“终端显示命令输出”与决策 D-08“结果摘要只占一行，不回显完整内容”有张力。现在按 D-08 实现：终端上只有“结果：退出码 0”，命令输出在会话记录里，模型的最终回复会转述它。如果你要终端直接显示，建议只回显输出的最后若干行（例如 20 行），超出时仍只给一行摘要；这是改决策，等你说。

## 阶段与退出条件

### A 协议与循环

- 退出条件：protocol 里有决定、等待批准的操作、批准来源和工具被中断时带出的结果；循环在工具被中断时如实记下它的结果，给后面的调用补“没有执行”，回合以取消结束；不联网的单元用例覆盖这几种转移。

### B 工具边界

- 退出条件：list_dir、write_file、run_command 可注册，都受工作目录边界约束（run_command 除外，R8.4）；危险等级按工具固定；执行前的批准是结构性的，没有批准来源就拒绝；越界和注定失败的写入不进入批准提示；退出码、输出、超时、截断、进程树各有用例。

### C 回合入口与终端

- 退出条件：`respond_action` 可用；批准项在执行之前落盘；拒绝后回合继续；一次响应里的多个危险操作逐个批准；批准提示的输入规则在交互循环、真实进程、真实控制台三层各有用例。

### D 夹具与冒烟

- 退出条件：mvp.json 录成；回放驱动三个回合走完整主链；冒烟脚本在回放下通过，`--live` 用真实模型跑过；verify-local 有 smoke:gate-b 任务；scripts 基线登记了 smoke 目录。

### E 规则、守卫与文档

- 退出条件：AGENTS.md 的审批硬规则与 governance.md 的守卫表同步；architecture.md 的第 3 节、7.1、7.3 与确认块备好；quality-workflow.md 绑定冒烟命令；契约重新登记；README 同步。

### F 验收与收尾

- 退出条件：路线图 P4 的四条退出条件逐条有结果；交付的需求逐条有验证记录；可追踪验收的分级结论写在本计划里；ruff 与 mypy 通过；门禁有结果。

## 逐条验证

路线图 P4 交付的需求逐条对应到用例。没写目录的用例在 tests/integration 下；写了 unit 的在 tests/unit 下。
模型除注明外都是测试替身。“真实子进程”指 tests/integration/test_run_command.py：工具经注册表执行，命令是真的在子进程里跑，不带模型。

| 需求 | 场景 | 用例 | 证据等级 |
| --- | --- | --- | --- |
| R5.4 | R5.4-S1 | unit 的 test_list_dir.py：test_files_and_a_subdirectory_come_back_with_their_kind、test_an_empty_path_lists_the_workdir | Unit |
| R7.1 | R7.1-S1、R7.1-S2 | unit 的 test_write_file.py：test_a_new_file_gets_exactly_the_given_bytes、test_line_feeds_are_not_converted；test_cli_process.py 里 hello.py 的逐字节核对 | Unit 加 Gate B |
| R7.2 | R7.2-S1 | unit 的 test_write_file.py：test_a_missing_parent_directory_is_an_error_and_nothing_is_written | Unit |
| R7.3 | R7.3-S1、S2、S3 | test_run_command.py：test_a_command_that_prints_and_exits_zero、test_a_command_that_fails_on_stderr、test_the_command_inherits_the_environment | 真实子进程 |
| R7.4 | R7.4-S1 | test_run_command.py：test_a_command_that_runs_too_long_is_terminated_with_its_output | 真实子进程 |
| R7.5 | R7.5-S1 | test_run_command.py：test_output_is_cut_to_the_last_10000_characters | 真实子进程 |
| R7.6 | R7.6-S1、S2 | test_approval.py：test_a_write_waits_for_approval_then_runs、test_read_only_tools_never_ask；test_run_command.py：test_a_command_is_not_started_until_it_is_approved；冒烟脚本对着会话记录断言每个危险调用都先有批准项、后有结果 | 入口集成加 Gate B |
| R7.7 | R7.7-S1、S2 | unit 的 test_write_file.py：test_the_prompt_shows_the_path_the_state_and_the_whole_content；test_approval.py：test_an_overwrite_is_announced；冒烟脚本核对终端上的提示 | Unit、入口集成、Gate B |
| R7.8 | R7.8-S1 | test_run_command.py 与 test_approval.py 各有一条 test_the_command_prompt_shows_the_command_verbatim；冒烟脚本 | 入口集成加 Gate B |
| R7.9 | R7.9-S1、S2 | test_cli_chat.py：test_y_at_the_approval_prompt_lets_the_write_run，test_anything_but_y_at_the_prompt_rejects（空输入、n、yes、Y、批准五个参数），test_input_end_at_the_approval_prompt_rejects；test_cli_process.py：test_n_at_the_prompt_leaves_the_file_unwritten；test_cli_console.py：test_y_typed_on_the_console_approves_a_write（真实控制台上输入 y） | 入口集成加 Gate B |
| R7.10 | R7.10-S1、S2 | test_approval.py：test_a_rejection_is_recorded_and_the_turn_goes_on、test_a_rejected_command_never_runs；冒烟脚本的拒绝断言；Live 冒烟 | 入口集成、Gate B、Live |
| R7.11 | R7.11-S1 | test_approval.py：test_two_dangerous_calls_are_approved_one_after_the_other；test_cli_process.py：test_two_prompts_in_one_turn_are_decided_separately_in_a_real_process | 入口集成加 Gate B |
| R7.12 | R7.12-S1 | test_approval.py：test_a_write_waits_for_approval_then_runs（批准项带时间、会话和回合，文件里也是这个顺序）、test_a_rejected_command_never_runs | 入口集成加 Gate A |
| R7.13 | R7.13-S1 | test_approval.py：test_a_rejection_is_recorded_and_the_turn_goes_on（模型的第二次请求里收到拒绝的结果，回合完成） | 入口集成 |
| R8.1 | R8.1-S1，list_dir 与 write_file | unit 的 test_list_dir.py：test_a_directory_inside_the_workdir_is_allowed；unit 的 test_write_file.py：test_a_file_in_a_subdirectory_is_allowed | Unit |
| R8.2 | R8.2-S1（list_dir）、R8.2-S2 | unit 的 test_list_dir.py：test_a_path_outside_the_workdir_is_refused；unit 的 test_write_file.py：test_a_path_outside_the_workdir_is_refused_without_asking；test_approval.py：test_an_out_of_bounds_write_never_reaches_the_prompt | Unit 加入口集成 |
| R8.3 | R8.3-S1、S2、S3，list_dir 与 write_file | 两个单元文件里各有三条：链接指向外部被拒、绕出去再回来允许、大小写不同的写法 | Unit，S3 只在 Windows 上运行 |
| R8.4 | R8.4-S1 | test_run_command.py：test_a_command_that_reaches_outside_the_workdir_still_asks | 真实子进程 |
| R12.5 | R12.5-S1 | unit 的 test_loop.py：test_a_tool_interrupted_midway_keeps_the_result_it_brings_back；test_run_command.py：test_ctrl_c_while_a_command_runs_terminates_it_and_keeps_its_output（模拟的 Ctrl+C）；test_cli_console.py：test_ctrl_c_while_a_command_runs_ends_the_whole_process_tree（真实的 Ctrl+C） | Unit、入口集成之下、Gate B |
| R14.1 | R14.1-S1 | test_fixture.py：test_the_recorded_replies_follow_the_report_rules（录下来的回复）；Live 冒烟的第 2 个回合 | Current fixture 加 Live |
| R14.2 | R14.2-S1 | 同上的第 1、3 个回合 | Current fixture 加 Live |

硬规则的守卫是冒烟脚本里的这一项：会话记录里每个危险调用都紧跟一条批准项和一条结果。
R14.3、R14.4 是"应当"，由路线图 P6 的评测验证（决策 D-12），本阶段不做断言；Live 冒烟的第 2 个回合里，
模型在回复里写明不会换一种做法绕过拒绝，这是观察，不是断言。

## 验证矩阵

全部命令在 2026-11-26 的工作树上跑。签署之前的那一轮设置 `UV_NO_SYNC=1`，原因写在进度记录里：当时仓库所有者有一个正在运行的 lime-star 会话占着入口命令，uv 重装不了它；这只跳过 uv 的同步步骤，不改任何检查。签署之后那个会话已经结束，全量门禁不设它重跑了一遍，结果在表里的最后一行。

| 阶段 | 命令 | 证据等级 | 结果 |
| --- | --- | --- | --- |
| A | `uv run pytest tests/unit/test_loop.py tests/unit/test_registry.py -q` | Unit，不联网 | 通过：14 条、24 条 |
| B | `uv run pytest tests/unit/test_list_dir.py tests/unit/test_write_file.py -q` | Unit | 通过：12 条、16 条 |
| B | `uv run pytest tests/integration/test_run_command.py -q` | 真实子进程，不带模型 | 通过：17 条，1 条跳过（只在 /bin/sh 上跑的那条） |
| C | `uv run pytest tests/integration/test_approval.py -q` | 入口集成，模型为测试替身 | 通过：13 条 |
| C | `uv run pytest tests/integration/test_cli_chat.py -q` | 入口集成，交互循环这一层 | 通过：27 条 |
| C | `uv run pytest tests/integration/test_cli_process.py -q` | Gate B，真实进程，模型为测试替身 | 通过：22 条 |
| C | `uv run pytest tests/integration/test_cli_console.py -q` | Gate B，真实控制台与真实的 Ctrl+C，模型为测试替身 | 通过：7 条 |
| D | `uv run python -m tests.integration.record_provider mvp` | Live，录制 | 通过：北京时间 2026-11-26 07:54，glm-5.2，三个回合共 7 次请求，全部完成；批准提示 4 次，交回批准 3 次、拒绝 1 次，没有触发"场景没有点名"的拦截 |
| D | `uv run pytest tests/integration/test_fixture.py -q` | Current fixture，模型为回放夹具 | 通过：4 条，运行前禁用全部 socket。回放时发给模型的内容与录制时逐项相同，系统指令除外 |
| D | `uv run python scripts/smoke/agent_gate_b.py` | Gate B，模型为回放夹具 | 通过：23 项检查，6.5 秒 |
| D | `uv run python scripts/smoke/agent_gate_b.py --live` | Gate B 加 Live，真实进程、真实模型 | 通过：20 项检查，26 秒，glm-5.2 |
| 全程 | `uv run pytest -q` | 汇总 | 345 条通过、1 条失败、3 条跳过（2 条 Live，1 条只在 /bin/sh 上跑）。失败的是 7.3 确认块的守卫，见下面"架构确认" |
| 全程 | `uv run pytest tests/integration/test_transcript.py -q` | Gate A 回归 | 通过：9 条，包含在全量里 |
| 全程 | `uv run ruff check .` 与 `uv run ruff format --check .` | 静态检查 | 通过：110 个文件 |
| 全程 | `uv run mypy`，另按 Linux 平台口径跑一次 | 类型检查 | 通过：66 个文件。冒烟脚本不在配置的检查范围里，另跑了一次：`MYPYPATH=. uv run mypy src scripts/smoke/agent_gate_b.py`，两种平台口径都通过 |
| E | `npm run test:contracts` | 契约 | 通过：契约 1 项，说明改了之后重新登记 |
| E | `node scripts/check-doc-links.mjs`、`check-file-size-governance.mjs`、`check-scripts-baseline.mjs` | 守卫 | 通过。行数门禁凭第一项里的 @generated 把 mvp.json 认作生成文件；scripts 基线多了一级目录 smoke |
| 全程 | 密钥守卫的 8 条规则，对本轮 44 个改动和新增的文件另扫一遍；两份夹具另查接口地址和主目录路径 | 守卫 | 0 处命中，夹具里没有。正式的密钥守卫只扫已跟踪的文件，新文件要等提交后才在它的范围内 |
| G | `npm run verify:local -- --full` | 门禁 | 签署之后重跑（2026-11-26 10:44，不设 UV_NO_SYNC）：12 个任务全部通过，约 200 秒。test:unit 346 条通过、3 条跳过；smoke:gate-b 23 项；test:guards 41 条；architecture 21 条。签署之前那一轮停在 test:unit 的确认块守卫上（345 通过、1 失败），fail-fast 之后的三个任务单独跑，其中两个各只有那一条失败 |

未跑与原因：

- CI：要等提交和推送，本轮没有提交。Linux 上的 run_command（/bin/sh、进程组）在本机跑不了，只有 CI 能验证；CI 的全量门禁会跑上面那些在两种平台上都能跑的用例。
- 真实控制台上批准提示处按 Ctrl+C：交互循环这一层（test_cli_chat.py）和入口集成都有用例，真实控制台里只验证了命令运行中的 Ctrl+C 和输入 y。
- 不设 `UV_NO_SYNC` 的门禁：已经跑过。那个会话结束之后 uv 补上了入口命令的重装，签署之后的全量门禁不设它，12 个任务全部通过。

## 验证合同

预算标签: budget:release（全量门禁加 Gate B 冒烟，另跑一次 Live）

主链: app 回合入口 `start_turn` -> agent_runtime 回合循环 -> tool_runtime（危险操作先经 app 的 `respond_action` 取得批准）-> thread_store（工具调用、批准、工具结果依次落盘）-> CLI 投影

Happy Path:

1. 配置齐全，在空目录里不带参数运行 lime-star。终端出现版本号、工作目录和输入提示。
2. 用户输入“新建一个脚本 hello.py，打印 hello，然后运行它，把结果告诉我。”。终端显示模型的动作；模型请求写文件时，终端出现批准提示，里面有路径、“新建文件”和完整的内容。
3. 用户输入 y。终端显示“已批准。”和一行结果摘要；hello.py 出现在磁盘上，会话记录里依次是工具调用、批准、工具结果。
4. 模型请求运行脚本，终端出现批准提示，显示原样的命令。用户输入 y。命令的输出记进会话记录，终端显示“退出码 0”。
5. 模型给出最终回复，说明做了什么、结果如何。用户在磁盘上打开会话记录，看到的顺序与终端一致。
6. 用户换个文件再来一次，在批准提示处输入 n。文件没有被写入，记录里有一条写明拒绝的批准项，模型的回复没有把它说成已完成。

Evidence Layers:

- 必须达到: Gate B（冒烟脚本，真实进程、真实输入、贯穿主链的可见输出；模型标注为回放夹具）。另跑一次 Live（冒烟脚本 `--live`，真实模型），用来验证 R14.1、R14.2 的行为。
- 禁止替代: 用集成测试里函数的返回值冒充真实进程证据；用回放夹具冒充真实模型；只看终端输出不核对会话记录。

必跑命令:

| 命令 | 目的 | 状态 |
| --- | --- | --- |
| `uv run pytest tests/unit -q` | 循环、注册表的批准、三个工具的纯逻辑、输出格式，不联网 | 通过：175 条。这一行只守循环、注册表的批准、list_dir 与 write_file 的纯逻辑；命令的输出格式要真跑命令，在 test_run_command.py 里 |
| `uv run pytest tests/integration/test_approval.py tests/integration/test_run_command.py tests/integration/test_tools.py -q` | 入口集成：经 app 回合入口的审批与工具 | 通过：13 条、17 条（另 1 条跳过）、7 条 |
| `uv run pytest tests/integration/test_cli_chat.py tests/integration/test_cli_process.py tests/integration/test_cli_console.py -q` | 交互循环、真实进程、真实控制台 | 通过：27 条、22 条、7 条 |
| `uv run pytest tests/integration/test_fixture.py -q` | Current fixture：回放驱动完整主链 | 通过：4 条，模型为回放夹具 |
| `uv run python scripts/smoke/agent_gate_b.py` | Gate B 冒烟（模型为回放夹具） | 通过：23 项检查 |
| `uv run python scripts/smoke/agent_gate_b.py --live` | Live：真实进程加真实模型 | 通过：20 项检查，glm-5.2 |
| `uv run pytest tests/integration/test_transcript.py -q` | Gate A：会话记录的事实不回归 | 通过：9 条 |
| `npm run test:contracts` | 契约检查 | 通过：契约 1 项 |
| `uv run ruff check .` 与 `uv run ruff format --check .` | 静态检查 | 通过 |
| `uv run mypy`，另按 Linux 平台口径跑一次 | 类型检查 | 通过 |
| `npm run verify:local -- --full` | 本地门禁 | 签署之后通过：12 个任务全部通过（2026-11-26）。签署之前停在确认块守卫上，见验证矩阵 |

未跑的命令在验证矩阵里写明原因和风险。

失败回写: 测试失败时三选一，修产品、修测试、补守卫。本轮的选择记在进度记录里。

完成标准:

- [x] 必跑命令全部有结果记录
- [x] 证据等级达到 Evidence Layers 要求：Gate B 与 Live 都已达到
- [x] 下一刀已写明

## 架构确认

```text
Architecture impact: major
架构图已更新：architecture.md 第 3 节加一条固定判断、第 7 节的 7.3；7.1 的指引改指 7.3
Responsible developer confirmation: 仓库所有者，2026-11-26
确认内容：本阶段不新增目录，也不改依赖矩阵：tool_runtime、app、cli 三个 owner 都已存在。改变的是业务主链：危险操作在执行之前多了一个节点，批准；回应它经 app 回合入口的 respond_action，循环对此一无所知。正式命令第一次向模型提供 write_file 和 run_command，第一次能在用户的工作目录里改动文件、执行命令。替代方案：让循环自己处理审批，循环就得知道危险等级和用户界面，被"循环是纯核心"禁止；让每个工具在执行函数里自己请求批准，那要靠自觉，所以改成注册表里的结构性保证，拿不到批准就不调用执行函数；结束命令的进程树用 taskkill，中间进程先退出时它的子进程会漏掉，所以 Windows 上用作业对象。回滚策略：默认工具集回到 read_file 和 list_dir，删除 write_file、run_command 和 Session.respond_action；已经写出的会话记录不需要迁移，批准项的形状从 P3 起就在契约里。
```

判定为重大的依据是 architecture.md 第 5 节的"改变业务主链"：主链上多了一个节点（批准），回应它是一个新的入口（respond_action）。确认块在 architecture.md 第 7 节 7.3 和本计划各有一份，内容相同；仓库所有者于 2026-11-26 回复"确认"，两处已一起签署，署名用"仓库所有者"，与 P2、P3 一致。签署之前本地门禁停在确认块的守卫上（345 通过、1 失败），那是"未确认的重大变更不得标记完成"的机械表现；签署之后 12 个任务全部通过。

## 可追踪验收

按 `../develop/traceable-acceptance.md` 做的一次验收，2026-11-26。阶段是验收：只判断，不顺手改代码。对象是 MVP 范围内的需求（R1 到 R8、R12、R13、R14）和需求全局文件里的主场景。R9 到 R11 属于 MVP 之后，不在这次验收里。

### 验收对象

作为开发者，我希望：让 Agent 新建一个脚本并运行它时，每次写文件和执行命令都先看到它要做什么，由我决定做不做；我拒绝时它不做，也不把这件事说成做完了。这样我才能放心让它在我的项目目录里动手。

### 主链与证据合同

| 节点 | current owner | 可观测证据 | 通过判据 | 失败分类 |
| --- | --- | --- | --- | --- |
| 1. 提交回合 | cli、app | 会话记录里的 turn_start、user_message；随后回到输入提示 | 回合有开始，用户的消息原样在记录里 | routing_gap |
| 2. 模型请求工具 | model_provider、agent_runtime | 会话记录里的 tool_call；请求日志的记录 | 模型的每次调用先落盘，再执行 | persistence_gap |
| 3. 批准提示 | tool_runtime 给出说明；cli 显示并读输入 | 终端输出里的说明和 `[y/n]` | 写文件显示路径、新建还是覆盖、全部内容；命令显示原样的一条 | projection_gap |
| 4. 决定落盘 | app、thread_store | 会话记录里紧跟调用的 approval 项 | 每个危险调用都有且只有一条批准项，决定做出之后才放行 | policy_gap |
| 5. 执行或拒绝 | tool_runtime | 磁盘上的文件；tool_result | 批准的执行了，结果与磁盘一致；被拒绝的没有执行，结果是拒绝 | persistence_gap |
| 6. 命令的输出 | tool_runtime | tool_result 里的退出码和输出 | 退出码和输出与事后独立再运行一次的结果一致 | evidence_gap |
| 7. 最终回复 | model_provider | model_text | 说的和记录一致：被拒绝的不说成已完成，失败的命令说失败 | eval_gap |
| 8. 回合收场 | agent_runtime、thread_store | turn_end；终端回到输入提示 | 每个回合都有结局项 | protocol_gap |

### 跑了哪些真实路径

1. `uv run python scripts/smoke/agent_gate_b.py`：真实的 lime-star 进程，模型为回放夹具，23 项检查通过。断言对着会话记录文件和磁盘，终端输出只用来核对批准提示。
2. `uv run python scripts/smoke/agent_gate_b.py --live`：真实的 lime-star 进程加真实模型 glm-5.2，20 项检查通过，8 次请求。第 3 个回合里模型先读了 fail.py 再运行它，和录制时不完全一样；各项检查照样通过，因为它们看的是事实，不是固定的步数。
3. 全量测试 345 条通过，其中包含 P1 到 P3 交付的需求的回归。

### 分级结论

主场景逐步：

| 步骤 | 结论 | 证据位置 | 说明 |
| --- | --- | --- | --- |
| 1. 终端显示 Agent 浏览或读取目录的动作 | Evidence Gap | Live 冒烟第 1 个回合的项 | 两次真实运行里模型都没有先列目录：目录里只有 fail.py，它直接写文件。终端显示了它的说明文字和工具调用。这是模型的选择，不是程序缺口；列目录本身有单元和入口集成的证据 |
| 2. 写文件的批准提示显示完整内容，输入 y | Pass | test_cli_process.py 的四条用例；冒烟的提示断言；会话记录里的 approval 项 | |
| 3. 运行脚本的批准提示显示原样命令，输入 y | Pass | 同上 | |
| 4. 终端显示命令输出；Agent 给出最终回复 | Partial | 冒烟里"运行 hello.py 经批准后执行，命令输出 hello 在会话记录里"一项；最终回复 | 回复有证据。终端上只有一行"结果：退出码 0"，命令输出在会话记录里。这是决策 D-08 的要求，和这一步的字面要求有张力，见"待仓库所有者决定"第 2 条。归类为 spec_gap |
| 5. 换个文件再试，在批准提示处输入 n | Pass | 冒烟的拒绝断言；test_the_recorded_replies_follow_the_report_rules；Live 冒烟的第 2 个回合 | 文件没有写入，回复里写的是"没有被创建" |

MVP 范围内的需求：

| 需求 | 结论 | 证据 | 说明 |
| --- | --- | --- | --- |
| R1、R2、R3 | Pass | P0 到 P2 留下的用例，本轮全量回归通过 | 本轮没有改动这些能力 |
| R4 | Pass | 同上；冒烟在回放和 Live 下各核对一次密钥不在终端输出和会话记录里 | |
| R5 | Pass | 逐条验证里的 R5.4；read_file 的三条沿用 P3 的证据 | |
| R6 | Pass | test_transcript.py 的 9 条 Gate A；test_a_write_waits_for_approval_then_runs 核对批准项在文件里的顺序 | |
| R7 | Pass | 逐条验证里的 R7.1 到 R7.13：单元、入口集成、真实子进程、真实进程、真实控制台、冒烟 | |
| R8 | Pass | 逐条验证里的 R8.1 到 R8.4 | 链接指向外部的条目在 Windows 上用的是目录联接，符号链接那一支没有跑过 |
| R12 | Pass | R12.5-S1 本轮补上：模拟的 Ctrl+C 和真实控制台的 Ctrl+C 都结束整棵进程树 | 取消的回合要不要让模型知道，仍待决定 |
| R13 | Pass | R13.8、R13.9 在批准提示处同样成立：提示之前到达的输入被丢弃并计数 | |
| R14 | Partial | R14.1-S1、R14.2-S1：录制的回复和 2026-11-26 的 Live 冒烟各一次 | R14.3、R14.4 没有断言，由路线图 P6 的评测验证（决策 D-12） |

总体是 Partial。主链的每个节点都有证据。没有到 Pass 的有两处：主场景第 4 步和决策 D-08 的张力，这是规格问题，等仓库所有者定；R14.3 和 R14.4 的评测，按计划在 P6。另外，路线图 P4 退出条件的第 1 条要求仓库所有者亲手完成一次主场景，那一步还没有发生，所以 SC-1 的"开发者至少拒绝一次"目前只有 Agent 替它跑出来的证据。

### 沉淀的回归资产

| 缺口 | 后续资产 |
| --- | --- |
| 主场景第 4 步与决策 D-08 的张力 | 等仓库所有者决定。定了之后只改 cli/chat.py 里投影的一处，冒烟加一项断言 |
| R14.3、R14.4 没有断言 | 路线图 P6 的评测；mvp.json 的第 2 个回合是一份可用的样本 |
| 真实运行里模型没有先浏览目录 | 人工观察，不扩大成任务 |
| 冒烟脚本不在 mypy 的配置范围里 | 技术债 CCD-005 |

## 进度记录

每刀一条，按日期追加，不改写历史。

### 2026-11-25

- 改动：产品代码。protocol 加了决定、等待批准的操作、批准来源和工具被中断时带回的结果；循环在工具被中断时如实记下它的结果；tool_runtime 加了 list_dir、write_file、run_command 和进程树，注册表在执行危险工具之前先取得批准；app 的 start_turn 多了提问回调，加了 respond_action；cli 加了批准提示和批准项的投影；系统指令写明四个工具和审批。
- 改动：测试。单元：test_list_dir.py、test_write_file.py，test_registry.py 和 test_loop.py 各补几条。入口集成：test_approval.py、test_run_command.py；test_cli_chat.py、test_cli_process.py、test_cli_console.py 各补批准与命令的用例。
- 验证：分层跑定向用例，全部通过。单元 175 条；test_approval.py 13 条；test_cli_chat.py 27 条；test_run_command.py 加两个工具的单元用例 45 条通过、1 条跳过；真实进程里批准的四条 12 秒；真实控制台 7 条跑了两遍，结果相同，两条新用例单独再跑一遍是 6.3 秒。
- 失败回写（修产品，一次）：Windows 上追加的退出码语句起初在"原生命令成功、后面一条 cmdlet 失败"时把退出码带成 0，改成只有非零的退出码才带出，其余失败一律 1。
- 失败回写（修测试，产品行为没有为这些失败改动）：list_dir 的排序期望写错，它按名称排，不是目录在前；留下后台进程的用例少了后台进程自己打印的那一行；test_approval.py 里几处期望写错，元组当成了列表，第二个回合的第一次请求是第 3 个请求。
- 失败回写（修测试夹具）：ScriptedLines 的 drain 本来就不丢行，别的用例靠它预先把 /exit 排进队列。核对"提示之前到达的输入不算回应"需要真的丢行，所以另加了照产品做法丢行的 QueuedLines，没有改它。
- 完成度：70%。产品代码和分层用例完成；夹具、冒烟脚本、规则与文档、验收还没有做。
- 下一刀：录 MVP 场景的夹具，写冒烟脚本，接进 verify-local，再补规则与文档。

### 2026-11-26

- 改动：夹具与回放。夹具改成多回合的形状，read_file.json 只重排、数据不变；录制脚本改成按场景录制，场景里每个回合对批准请求只有一种做法，真实模型面前只放行场景点名的操作；ReplayServer 给真实的进程回放。新夹具 mvp.json 是从真实模型录的三个回合，第一项带 @generated 标记，行数门禁据此把它认作生成文件。
- 改动：冒烟与门禁。scripts/smoke/agent_gate_b.py 新建，默认回放夹具，`--live` 用真实模型，断言对着会话记录和磁盘；verify-local 的任务表加了 smoke:gate-b；scripts 基线多了一级目录 smoke。
- 改动：规则与文档。根 AGENTS.md 加入审批硬规则；architecture.md 第 3 节加一条固定判断，追加 Owner 章节 7.3 和确认块；governance.md 的守卫表、quality-workflow.md 的矩阵各一行；thread-items 契约的说明改了，形状没变，重新登记；根 README、scripts/README、本目录的 README；技术债登记 CCD-005。
- 改动：测试工具。CliProcess.close 从只结束启动器改成结束整棵进程树：用例失败时不再留下一个一直等输入的会话进程。
- 验证：逐项结果见验证矩阵，需求与用例的对应见"逐条验证"，验收结论见"可追踪验收"。门禁停在 7.3 的确认块守卫上，那是这一刀唯一的一条失败。
- 失败回写（修测试，产品行为没有为这些失败改动）：默认工具集从只有 read_file 变成四个工具，test_loop.py 里对应的用例随之改；夹具用例起初核对写死的项序列，真实模型在调用工具前先说话，序列不是固定的，改成核对结构；mvp.json 有 1329 行，被行数门禁拦下，它是录下来的数据，按门禁原有的 @generated 机制标注为生成文件。
- 真实接口上看到的事实（glm-5.2，录制一次、Live 冒烟一次，共 15 次请求）：
  1. 主场景一次走通：写 hello.py，运行 `python hello.py`，回复里写了退出码 0 和输出 hello。
  2. 写文件被拒绝之后，模型的回复写明"文件没有创建""没有执行运行步骤"，还主动说明不会换用命令行重定向来绕过拒绝（R14.3 的做法，观察，没有做成断言）。
  3. 以退出码 1 结束的命令，回复里指出失败，并列出退出码、标准输出和标准错误；标准错误里的中文经 Windows PowerShell 原样带回，没有乱码。
  4. 模型在调用工具之前先说一段话，所以会话记录里是 model_text、tool_call、approval、tool_result 这样交替，不是固定的形状。冒烟和夹具用例因此核对结构，不核对写死的序列。
  5. 两次真实运行里模型都没有先列目录，直接写文件。Live 冒烟的第 3 个回合它先读了 fail.py 再运行，和录制时不一样。
  6. 四次批准提示都是场景点名的操作，"场景没有点名就拒绝"的拦截一次也没有触发。
- 观察到但没有处理：
  1. 仓库所有者有一个 2026-11-25 07:49 在 VS Code 的终端里启动的 `uv run lime-star` 会话还在运行，占着 .venv 下的 lime-star.exe。我一度改了 pyproject.toml（想让 mypy 也检查冒烟脚本），uv 因此要重装入口命令，被它挡住；pyproject.toml 已经恢复成和 HEAD 一样，但 uv 缓存里的条目换过了，在那个会话结束之前，不带 `--no-sync` 的 `uv run` 都会在这一步失败。本轮的验证都是在 `UV_NO_SYNC=1` 下跑的。那个会话我没有动。
  2. 调用 write_file 时，终端先显示一整行转义的 JSON 参数，紧接着是可读的批准提示，内容出现了两遍。内容长的时候那一行很长。
  3. 真实控制台上批准提示处的 Ctrl+C 没有专门的用例；交互循环这一层和入口集成有。
  4. 冒烟脚本是 Python，但不在 mypy 配置的检查范围里，lint 和 typecheck 任务也不随 scripts/ 的改动触发，登记为 CCD-005。
  5. 录下来的夹具有 55871 个字符。再录几个场景之后，仓库里的夹具会变大；那时可以考虑把请求里的系统指令去掉再存，它每次都一样。
- 完成度：Agent 侧的工作完成。P4 整体 90%，剩下的取决于仓库所有者：亲手完成一次主场景，签署架构确认，对"待仓库所有者决定"的两条给出答复，提交之后看 CI。
- 下一刀：仓库所有者按路线图 P4 的验收动作核对；说"确认"之后我把两处确认块署上"仓库所有者"和日期，重跑门禁；说"提交"再提交。CI 通过之后在路线图追加 P4 的阶段结论，关闭本计划，然后按 P5 的开工话术开始 P5。

### 2026-11-26（架构确认）

- 改动：仓库所有者回复"确认"。architecture.md 第 7 节 7.3 和本计划的确认块都已签署，署名用"仓库所有者"，与 P2、P3 一致。产品代码和测试没有改。
- 验证：签署之后，不设 `UV_NO_SYNC` 跑 `npm run verify:local -- --full`，12 个任务全部通过，约 200 秒。test:unit 346 条通过、3 条跳过（Live）；smoke:gate-b 23 项通过，模型为回放夹具；test:guards 41 条；architecture 21 条。那个旧会话已经结束，uv 在这一轮里补上了入口命令的重装，`uv run` 不再需要 `--no-sync`。
- 未跑：CI，它只能在提交和推送之后跑。
- "待仓库所有者决定"的两条：这次的回复只有"确认"两个字，没有提到它们，两条都保持现状，不改代码。
- 完成度：95%。还差 CI。路线图 P4 退出条件的第 1 条要仓库所有者亲手做，回复里没有说他做了没有。
- 下一刀：仓库所有者说"提交"再提交，push 要他单独要求。推送之后核对 CI，通过就在路线图追加 P4 的阶段结论，关闭本计划。那两件待定的事和 CCD-005 最好在 P5 开工之前处理。

## 当前结论

- 治理四分类：current 新增 tool_runtime 的 list_dir、write_file、run_command，进程树 Tree，Tool 的 danger，Registry.approved_by 和它返回的 Granted；protocol 的 Pending、Approver、Decision、Halted；app 的提问回调和 Session.respond_action；cli 的批准提示和批准项的投影；scripts/smoke/agent_gate_b.py 和 verify-local 的 smoke:gate-b 任务；测试里的回放服务、按场景的录制和 mvp 夹具。current 扩展：循环对被中断的工具的处理，默认工具集，系统指令，thread-items 契约的说明，CliProcess 的收尾。compat、deprecated、dead 均无新增或删除。直接替换掉的内部做法不属于四类：夹具的单回合形状，录制脚本里写死的一段对话，CliProcess.close 只结束启动器的做法。
- 验证结果与未验证原因：见验证矩阵。路线图 P4 的四条退出条件逐条有结果。第 1 条（仓库所有者亲手完成主场景并至少拒绝一次）：Agent 用真实进程替它跑了两次，一次模型为回放夹具，一次是真实模型；仓库所有者自己有没有亲手跑，回复里没有说。第 2 条（交付需求逐条有验证记录）见"逐条验证"，R14.3、R14.4 按决策 D-12 留给 P6。第 3 条（冒烟脚本）通过。第 4 条（可追踪验收）的结论是 Partial，见"可追踪验收"。未验证：CI，Linux 上的 run_command，真实控制台上批准提示处的 Ctrl+C。架构确认块已由仓库所有者于 2026-11-26 签署，本地门禁 12 个任务全部通过；CI 还没有跑。
- 未做与原因：pyproject.toml 没有把 scripts 加进 mypy 的检查范围，冒烟脚本只在本轮手工检查过一次，登记为 CCD-005。
- 来源声明：对照阅读了 lime 仓库 internal/aiprompts/query-loop.md 的"代码入口地图"和"current / compat / deprecated"，以及 lime-rs/crates/tool-runtime 的目录结构，和其中 execution_approval.rs、execution_decision.rs、unified_exec/cancellation.rs、path_guard.rs 的文件头。只取三个思路：批准是主链上一个可以恢复的节点，回应它只复用当前回合的上下文；要不要批准由工具边界在执行前按工具判定，判定和执行在同一个 owner；取消时先结束进程树，再把已有的输出作为结果写下来。按本仓库语境重写，没有复制原文。Windows PowerShell 的退出码、标准错误、引号传递和作业对象的行为是本机用临时脚本实测的，脚本在仓库外，没有入库；它们还在系统临时目录的 lime-star-p4-exp 下（约 16 KB），删除它的命令被本机的策略拦下，可以手动删。真实模型只用于录制夹具和一次 Live 冒烟。

完成度: 95%
