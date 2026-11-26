# p5-resume 计划

状态: done
日期: 2026-11-26
主目标: 进程退出或被中断之后，`lime-star --resume` 从会话记录恢复同一个会话并接着对话；没有正常结束的回合被判为中断，恢复后不自动续跑（Gate B）。

## 目标

开发者在项目目录里用 `lime-star` 聊过几句，关掉终端，或者在回合进行中按 Ctrl+C，或者进程被强制结束。之后在同一个目录里运行 `lime-star --resume`：终端用一行说明恢复了哪个会话、它已经有几个回合；上一个回合没有完成时，再一行写明原因，比如是用户取消的，还是进程在等待批准时被结束、那次操作没有执行。随后回到输入提示，下一条消息接着原来的上下文。恢复后的进程不会自己接着跑那个没完成的回合，不会再问一次悬着的批准，也没有执行任何操作。这一切只凭磁盘上的会话记录做到，不依赖旧进程留下的任何东西。

## 当前事实

- 仓库所有者于 2026-11-26 说"开始P5"。开工前检索未决项（`rg "^未决 OQ-" internal/prd`），没有命中。
- 工作树干净，HEAD 是 aabd11b。基线：`uv run pytest -q` 是 346 条通过、3 条跳过（Live），约 156 秒。
- P4 的状态：代码已交付并推送（提交 90e48a1，CI 通过），p4-tools-approval 计划还开着，等仓库所有者答复两件事。开始 P5 不等于把 P4 记为完成：路线图里 P4 的阶段结论和关闭 P4 的计划，仍然等那两件答复，以及他亲手完成一次主场景。两件事登记在下面"待仓库所有者决定"。
- P4 留下的形态：`open_session` 每次新建一个会话，标识由 uuid 生成；`Session.start_turn` 在每个回合开始时从文件读出全部历史交给循环；`thread_store` 只有 `Transcript` 的追加与读回，以及按文件读回的 `read`；等待中的批准只在内存里，进程在等待时被结束，记录里只有工具调用，没有批准项和结果（architecture.md 的 7.3）；循环在取消时给没有执行的调用补一条出错的结果；回合结局有四种；CLI 的 `chat` 先显示一行版本号和工作目录，再把落盘的项投影到终端。
- 路线图 P4 的"下一刀"带过来三件事，本计划都要处理：
  1. "取消的回合要不要让模型知道"从 P2 起待定，没有答复。本计划保持现状：回合结局项不上线路。见"待仓库所有者决定"第 1 条。
  2. 技术债 CCD-005 并入本计划清退：P5 新增第二个冒烟脚本，它应当一开始就在 mypy 的检查范围里，改 `scripts/smoke/` 也应当触发 lint 和 typecheck。
  3. 自动化脚本以输入提示为同步点；Windows 上 lime-star 是启动器，会话进程是它的子进程，强制结束要结束整棵进程树。冒烟脚本照此写。
- P3 计划里"由读取的一方在 P5 判为中断"留到这里：进程被强制结束时，回合有开始、没有结局，读记录的一方把它判为中断。
- 需求没有覆盖、本阶段躲不开的一件事：`--resume` 是第一条让第二个进程打开已有会话记录的路径。如果最近那个会话的进程还活着，恢复的进程会把一个正在进行的回合判成中断并替它收尾，原来的进程接着往一个已经收尾的回合里写，记录就坏了。处理办法见"本阶段的默认选择"第 7 条。
- 动手前在本机核实的事实（临时脚本，仓库外，事后已删）：Windows 上 `msvcrt.locking` 对空文件的第 1 个字节加锁成功；同一进程的另一个句柄被拒（PermissionError 13）；子进程持有时父进程被拒；子进程被结束之后马上可以再加锁。被锁住的那一个字节，别的句柄读它会失败，所以锁不加在会话记录文件上，另建一个锁文件。其他平台的 flock 分支在本机跑不了，只能由 CI 覆盖。
- lime 对照阅读（只读，仓库位置见 architecture.md）：lime-rs/crates/thread-store 的目录结构，lib.rs 与 store.rs 的文件头（存储边界只交换规范的 Thread、Turn、Item 值，文件路径不出这个边界；列出和读取线程是存储自己的事），history/replay.rs 与 runtime_snapshot.rs 的文件头（冷回放失败时整个丢弃，调用方看不到半套用的状态；恢复比较用已落盘的序号），internal/aiprompts/query-loop.md 里关于恢复路径的条目（恢复只能复用当前回合的上下文，不旁路拼第二份）。取三个思路，按本仓库语境重写，没有复制原文：
  1. 会话放在哪里、怎样找出最近的一个、怎样读回，都是 thread_store 的事；app 回合入口和 CLI 只拿到会话标识和项，不扫目录。
  2. 判定只从已经落盘的项出发，每次重新读文件来算，补记只写缺的那几项。补到一半进程又没了，下一次恢复照文件里剩下的再算，写下的每一句仍然属实。
  3. 恢复后的对话沿用从同一份会话记录派生的上下文，转换仍只有 model_provider 的一处，不另拼一份。

## 写集与避让

### 本轮认领写集

新建：

- src/lime_star/thread_store/ 下的 hold.py、threads.py、turns.py：会话记录的独占写入、最近一个有活动的会话、回合的读模型。
- scripts/smoke/resume_gate_b.py：恢复的 Gate B 冒烟。它进已有的 smoke 目录，scripts 基线不变。
- tests/unit/test_thread_store.py：会话查找、独占写入和读模型的单元测试。
- tests/integration/ 下的 test_resume.py、test_cli_resume.py、smoke.py：从 app 回合入口恢复的入口集成（持久化硬规则的守卫在这里）、真实进程里的 `--resume`、两个冒烟脚本共用的小工具。
- tests/fixtures/provider/resume.json：从真实模型录制的恢复场景。
- 本计划。

修改：

- src/lime_star/protocol/items.py：结局加一种 interrupted。protocol/thread-items.schema.json：结局的枚举同步，重新登记契约。
- src/lime_star/tool_runtime/registry.py：`Registry.dangerous()`，说出哪些工具要先经批准。
- src/lime_star/app/ 下的 session.py、__init__.py：`resume_session`、恢复时得到的概况、没有可恢复的会话、会话持有独占写入、`Session.close`。
- src/lime_star/cli/ 下的 main.py、chat.py：`--resume`、恢复时的一行说明和未完成的提示、interrupted 的投影。
- src/lime_star/thread_store/__init__.py：导出。
- pyproject.toml：mypy 的检查范围加 scripts（CCD-005）。
- scripts/verify-local.mjs（共享热区里的根脚本）：任务表加 smoke:resume，lint 和 typecheck 的触发路径加 scripts/smoke/。本轮没有其他 Agent 在工作。
- scripts/smoke/agent_gate_b.py：四个共用的小工具改为从 tests/integration/smoke.py 导入，行为不变。
- tests/integration/ 下的 support.py（模拟进程被结束、带参数启动进程）、conftest.py、replay.py（夹具里的若干段）、record_provider.py（分段录制、模拟进程被结束、恢复场景）、test_fixture.py（恢复场景的回放）、test_cli_process.py、test_cli_chat.py、test_cli_console.py、test_transcript.py（一句注释）。
- tests/unit/ 下的 test_cli_args.py、test_thread_items_schema.py。
- governance/contracts-state.json：由 `node scripts/check-contracts.mjs --update` 生成。
- 根 AGENTS.md（共享热区）：加入持久化硬规则。
- internal/aiprompts/architecture.md（共享热区）：目录地图三行、第 3 节加一条固定判断、追加 Owner 章节 7.4 与确认块。
- internal/aiprompts/governance.md：守卫表一行。internal/aiprompts/quality-workflow.md：业务主链一行加上恢复的冒烟命令。
- README.md、scripts/README.md、本目录的 README.md。
- internal/exec-plans/tech-debt-tracker.md：CCD-005 清退。

### 只读避让写集

- ../prd/：需求已确认，不改。需求没有覆盖的情形写在"本阶段的默认选择"，由仓库所有者在架构确认时一并核对。
- ../roadmap/agent-practice.md：路线图是只读避让集。阶段结论等仓库所有者验收、CI 通过之后再追加。
- p4-tools-approval-plan.md：P4 的计划还开着，等仓库所有者答复；本计划不改它。
- governance/ 下的 scripts-baseline.json、file-size-baseline.json、contracts.json：本轮不改。锁文件是运行时产物，不进仓库。
- scripts 下其余脚本，.github/workflows/quality.yml：它跑 verify:local 的全量，新任务自动进入。
- ../develop/、../research/、../tech/：只按它们的方法做验收，不改。

## 删除集

- tests/integration/test_cli_process.py 里的 test_help_does_not_list_resume_yet：它守的是"`--resume` 交付之前帮助里不列它"这条边界，交付之后不再成立，由"帮助里列出 --resume"取代。
- agent_gate_b.py 里的 Checks、SmokeFailure、wait_for_any、lime_star 四个小工具：挪到 tests/integration/smoke.py，不是能力退役。

## 本阶段的默认选择

1. 恢复只走 app 回合入口：`resume_session` 找出工作目录下最近的会话，读回它的记录，在同一个会话标识上接着写。CLI 只负责传 `--resume` 和显示。不带参数的 `open_session` 不变，仍然每次新建一个会话。
2. "最近一个有活动的会话"以会话记录里最后一项的时间为准，不看文件的修改时间：活动是记录里的事实，复制目录或还原文件不改变它。没有完整项的文件不算有活动，跳过。
3. 有开始、没有结局的回合由读取的一方判为中断（R9.3）。恢复的进程把这个判定写进同一份记录：没有结果的调用各补一条结果，最后补一条中断结局。结局多一种 `interrupted`，和"用户取消"分开：不是用户按的 Ctrl+C，以后按结局统计时也不用去读原因那一句话。
4. 补上的结果分三种，都是看记录就能确定的事实：
   - 危险工具的调用没有批准项：注册表不拿到批准就不调用执行函数，所以这次操作没有执行。原因写"进程没有收尾就结束了，当时正在等待批准 {工具名}，这次操作没有执行"（R9.4-S1）。
   - 危险工具的调用有批准项、没有结果：操作可能已经发生。原因写"进程没有收尾就结束了，{工具名} 已获批准却没有留下结果，这次操作可能已经发生"。
   - 别的没有结果的调用，或者一个都没有：原因写"进程没有收尾就结束了，当时没有等待批准或执行中的危险操作"。
5. 补记只对最后一个回合做。记录的中间出现"有开始、没有结局"的回合，说明它被改过或者被两个进程同时写过，按记录读不懂处理，拒绝恢复。
6. 恢复之前核对记录：每一项的会话标识与文件名一致，序号从 1 起连续；对不上就拒绝恢复，不往上写。
7. 一个会话记录同一时刻只有一个写入者。打开会话（新建或恢复）时在 .lime-star/locks 下取一个锁文件，用操作系统的文件锁占住，进程结束时自动释放。恢复时发现锁被占着，说明那个会话的进程还活着，退出码 1，说明"会话正被另一个进程使用"。这是需求没有写、本阶段默认采用的约束，写进了 7.4 的确认块。
8. 恢复时照常显示版本号和工作目录那一行，随后是 R9.1 的一行说明"已恢复会话 {标识}，已有 N 个回合"。不重放之前的任何输出（R9.5-S2）。
9. 上一个回合的结局不是完成时，再显示一行"上一个回合没有完成：{原因}"。取消、出错、步数上限取结局项里写的原因，中断取第 3、4 条判出来的原因。
10. 模型可见的历史不变：回合结局项仍然不上线路。补记的工具结果在记录里，所以模型在下一次请求里看得到"没有执行"或"结果未知"，恢复之后的如实报告有依据（R14.1）。
11. 没有可恢复的会话是用法错误：退出码 2，标准错误说明没有可恢复的会话，不建运行时目录，不发请求（R9.1-S2）。会话被别的进程占着、记录读不懂或对不上，是运行期错误：退出码 1，同样不往上写。恢复之前先找会话，再读模型配置：没有会话时提示的是真正缺的东西。
12. 模型配置不随会话保存，恢复时重新读取（R9.5、R4.1）。请求日志里恢复后的记录带新的 session_id 和原来的 thread_id，凭它们分得清恢复前后的请求。
13. 冒烟脚本 scripts/smoke/resume_gate_b.py 默认回放录制的夹具，加 `--live` 用真实模型。verify-local 的任务表加 smoke:resume。两个冒烟脚本共用的小工具挪到 tests/integration/smoke.py，冒烟脚本继续借用 tests 里驱动真实进程和回放的小工具（P4 的做法）。
14. 夹具在原来的形状上加一个可选的 runs：若干段，每一段相当于一个进程，写明它是新会话还是恢复，以及它跑 turns 里的哪几个回合。没有 runs 的夹具是一段新会话，已有的两份夹具不用重录。
15. 录制里的"进程被结束"在进程内模拟：第一次等待批准时抛出一个不是 Exception 的中断，注册表和循环都不接它，回合就地停住，什么也不补写，记录里留下的项与真实进程被结束时相同。真正的跨进程证据由真实进程的用例和冒烟脚本提供。

## 待仓库所有者决定

1. 取消的回合要不要让模型知道。P2、P3、P4 的计划里都提过，还没有答复。本计划保持现状：回合结局项不上线路。P5 之后它多了一层事实：中断的回合在恢复时补上了工具结果（"没有执行"或"结果未知"），模型看得到这些结果，但看不到回合的结局，包括新加的 interrupted。要改的话只动 model_provider 里 `_messages` 一处，把结局项转成一条说明；代价是录好的三份夹具都要重录。
2. P4 留下的两件事本计划不处理，只登记：主场景第 4 步与决策 D-08 的张力；路线图 P4 退出条件第 1 条要求你亲手完成一次主场景。定了之后在路线图把 P4 记为完成，关闭 p4 的计划。

## 阶段与退出条件

### A 协议与会话记录

- 退出条件：结局有 interrupted，契约重新登记；thread_store 能找出最近一个有活动的会话、能独占一个会话记录、能把有开始、没有结局的回合判为中断并给出要补的项；不联网的单元用例覆盖这些。

### B 回合入口

- 退出条件：`resume_session` 在同一个会话标识上接着写，恢复前核对记录、补记中断的回合；不自动续跑，不发请求；一个会话同时只有一个写入者；配置重新读取；入口集成的用例从 app 回合入口覆盖这些，其中有"写入后以新实例读取"。

### C 终端

- 退出条件：`--resume` 可用，帮助里列出它；没有会话时退出码 2；恢复时显示一行说明和未完成的原因，不重放历史；交互循环、真实进程、真实控制台三层各有用例。

### D 夹具与冒烟

- 退出条件：resume.json 录成；回放驱动三段恢复走完整主链；冒烟脚本在回放下通过，`--live` 用真实模型跑过；verify-local 有 smoke:resume 任务；CCD-005 清退。

### E 规则、守卫与文档

- 退出条件：AGENTS.md 的持久化硬规则与 governance.md 的守卫表同步；architecture.md 的目录地图、第 3 节、7.4 与确认块备好；quality-workflow.md 绑定冒烟命令；README 同步。

### F 验收与收尾

- 退出条件：路线图 P5 的四条退出条件逐条有结果；交付的需求逐条有验证记录；可追踪验收的分级结论写在本计划里；ruff 与 mypy 通过；门禁有结果。
## 逐条验证

路线图 P5 交付的需求逐条对应到用例，用例名称已按实际文件核对。
模型除注明外都是测试替身。"真实进程"指 tests/integration/test_cli_resume.py：两个真实的 lime-star 进程先后在同一个工作目录里运行。

| 需求 | 场景 | 用例 | 证据等级 |
| --- | --- | --- | --- |
| R9.1 | R9.1-S1 | unit 的 test_thread_store.py：test_the_latest_session_is_the_one_whose_last_item_is_newest、test_the_latest_of_two_sessions_is_the_later_one；test_resume.py：test_the_last_session_that_was_active_is_resumed；test_cli_resume.py：test_resume_picks_the_last_session_that_was_active；冒烟的"两个会话之后 --resume 恢复的是最后有活动的那个" | Unit、入口集成、Gate B |
| R9.1 | R9.1-S2 | test_resume.py：test_nothing_to_resume_is_a_usage_error；test_cli_resume.py：test_resume_without_a_session_exits_two；冒烟开头的两项 | 入口集成、Gate B |
| R9.1 | R9.1-S3 | test_cli_process.py：test_help_lists_resume；冒烟的第一项 | Gate B |
| R9.2 | R9.2-S1 | test_resume.py：test_a_new_instance_reads_back_what_was_written_and_goes_on；test_cli_resume.py：test_a_new_process_resumes_the_history_and_goes_on；test_fixture.py：test_the_recorded_resume_runs_drive_the_whole_chain；冒烟回放与 `--live` 的"模型的回答里有之前说过的名字" | 入口集成、Current fixture、Gate B、Live |
| R9.3 | R9.3-S1 | P4 留下的 test_cli_console.py：test_ctrl_c_while_a_command_runs_ends_the_whole_process_tree（结局项当场写明取消）；本轮新增 test_resume_after_ctrl_c_while_a_command_ran_says_it_was_cancelled | Gate B（真实控制台） |
| R9.3 | R9.3-S2 | unit 的 test_thread_store.py：test_a_dangerous_call_waiting_for_approval_was_not_executed、test_an_approved_call_without_a_result_may_have_run；test_resume.py：test_a_turn_cut_off_at_an_approval_is_closed_and_explained、test_an_approved_operation_cut_off_midway_is_reported_as_unknown；test_cli_resume.py：test_resume_after_the_process_was_killed_at_the_prompt；冒烟的"被结束的进程"两项和"记录：中断的回合补上了……" | Unit、入口集成、Gate B |
| R9.4 | R9.4-S1 | test_resume.py：test_a_turn_cut_off_at_an_approval_is_closed_and_explained（恢复没有请求模型，操作没有执行）；test_cli_resume.py：test_resume_after_the_process_was_killed_at_the_prompt（没有批准提示，模型只被请求过一次，文件没有被写）；冒烟的"恢复：没有续跑，没有请求批准，也没有再请求模型" | 入口集成、Gate B |
| R9.4 | R9.4-S2 | test_resume.py：test_resume_after_a_cancelled_turn_says_it_was_cancelled；test_cli_chat.py：test_resume_shows_the_recap_and_why_the_last_turn_did_not_finish；test_cli_console.py：test_resume_after_ctrl_c_while_a_command_ran_says_it_was_cancelled | 入口集成、Gate B |
| R9.5 | R9.5-S1 | test_resume.py：test_a_new_instance_reads_back_what_was_written_and_goes_on（硬规则的守卫：写入后以新实例读取，读到的与文件逐项一致）、test_the_live_session_rereads_the_file_for_every_turn | 入口集成 |
| R9.5 | R9.5-S2 | test_cli_chat.py：test_resume_shows_the_recap_and_why_the_last_turn_did_not_finish、test_resume_of_a_finished_session_shows_one_line_only；test_cli_resume.py：test_a_new_process_resumes_the_history_and_goes_on；冒烟的"恢复：终端是横幅、一行说明、输入提示、回答、输入提示，没有重放之前的输出" | 入口集成、Gate B |
| R9.5 | 陈述：模型配置不随会话保存 | test_resume.py：test_the_model_config_is_read_again；test_cli_resume.py：test_resume_with_a_missing_config_exits_two | 入口集成、Gate B |

"本阶段的默认选择"第 7 条（一个会话记录同一时刻只有一个写入者）不在需求里，它的用例：unit 的 test_thread_store.py 里 test_a_hold_is_exclusive_and_released、test_the_lock_directory_is_created_on_demand；test_resume.py：test_a_thread_has_one_writer_at_a_time；test_cli_resume.py：test_resume_is_refused_while_the_session_is_still_open。请求日志带新的会话标识和原来的线程标识（R3.4）：test_resume.py 的 test_the_request_log_keeps_the_thread_and_takes_a_new_session。

## 验证矩阵

全部命令在 2026-11-26 的工作树上跑。实现之前先跑过一次基线：`uv run pytest -q` 是 346 条通过、3 条跳过（Live），约 156 秒。

| 阶段 | 命令 | 证据等级 | 结果 |
| --- | --- | --- | --- |
| A | `uv run pytest tests/unit/test_thread_store.py tests/unit/test_cli_args.py tests/unit/test_thread_items_schema.py -q` | Unit，不联网 | 通过：22 条、12 条、14 条 |
| B | `uv run pytest tests/integration/test_resume.py -q` | 入口集成，模型为测试替身 | 通过：14 条 |
| C | `uv run pytest tests/integration/test_cli_chat.py tests/integration/test_cli_resume.py -q`；`uv run pytest tests/integration/test_cli_console.py tests/integration/test_cli_process.py tests/integration/test_transcript.py -q` | 交互循环这一层；Gate B（真实进程与真实控制台），模型为测试替身 | 通过：前一条 36 条（30 加 6），后一条 39 条（8 加 22 加 9） |
| D | `uv run python -m tests.integration.record_provider resume` | Live，录制 | 通过：北京时间 2026-11-26 14:05，glm-5.2，六个回合共 7 次请求；五个正常完成，一个在等待批准时进程被结束（录制里是模拟的）。写入 resume.json，1107 行，第一项带 @generated 标记。录制之前先用替身模型把录制流程空跑了一遍（仓库外的临时脚本，事后已删），没有消耗额度 |
| D | `uv run pytest tests/integration/test_fixture.py -q` | Current fixture，模型为回放夹具 | 通过：5 条，运行前禁用全部 socket。回放时发给模型的内容与录制时逐项相同，系统指令除外 |
| D | `uv run python scripts/smoke/resume_gate_b.py` | Gate B，模型为回放夹具 | 通过：26 项检查 |
| D | `uv run python scripts/smoke/resume_gate_b.py --live` | Gate B 加 Live，真实进程、真实模型 | 通过：21 项检查，glm-5.2。请求数没有单独记录 |
| D | `uv run python scripts/smoke/agent_gate_b.py` | MVP 的冒烟不回归 | 通过：23 项，模型为回放夹具 |
| E | `npm run test:contracts` | 契约 | 通过：契约 1 项。结局的枚举变了，已用 `--update` 重新登记 |
| E | `node scripts/check-doc-links.mjs`、`check-file-size-governance.mjs`、`check-scripts-baseline.mjs`、`scripts/security/check-secrets.mjs` | 守卫 | 通过。resume.json 凭 @generated 豁免行数门禁；scripts 基线没有变。密钥守卫只扫已跟踪的文件，新文件另查了一遍：夹具里没有密钥、接口地址和主目录路径 |
| 全程 | `uv run ruff check .` 与 `uv run ruff format --check .` | 静态检查 | 通过 |
| 全程 | `uv run mypy`，另按 Linux 平台口径跑一次 | 类型检查 | 通过：75 个文件。冒烟脚本从本轮起在检查范围里（CCD-005） |
| 全程 | `node scripts/verify-local.mjs --full` | 门禁 | 签署之后通过（2026-11-26）：13 个任务全部通过，约 4 分钟。test:unit 397 条通过、3 条跳过（Live）；smoke:gate-b 23 项；smoke:resume 26 项；test:guards 41 条；architecture 21 条。签署之前停在 test:unit 的确认块守卫上（396 通过、1 失败），之后的四个任务单独跑，只有那一条失败 |
| 全程 | CI：推送之后 GitHub Actions 的运行 45798785239，针对提交 033df27 | 门禁，Linux runner | 通过：verify 作业的每一步都成功，Local gate (full) 在 Linux 上通过，约 2 分钟。这是恢复的代码、锁的 flock 分支和恢复的冒烟第一次在 Windows 以外运行。依据是运行、作业和步骤的状态，日志没有读，所以 Linux 上逐条用例的结果没有记录 |

未跑与原因：

- CI 已经通过，见表里最后一行。锁的 flock 分支本机跑不了，由那次全量门禁覆盖：入口集成、真实进程的用例和恢复的冒烟都经过取锁和放锁。日志没有读，Linux 上逐条用例的结果没有记录。
- 真实控制台上批准提示处的 Ctrl+C 之后的恢复：交互循环和入口集成有用例，真实控制台里只验证了命令运行中的 Ctrl+C。管道驱动和冒烟脚本都发不出真实的 Ctrl+C。
- 真实模型上"已获批准的操作在执行途中被结束"之后的恢复：Live 只跑了"等待批准时被结束"这一种；另一种只有替身工具的入口集成证据。
- `--live` 冒烟的请求数：脚本不打印它，这次没有单独记录。

## 验证合同

预算标签: budget:release（全量门禁加两个 Gate B 冒烟，另跑一次 Live）

主链: CLI 的 `--resume` -> app 回合入口 `resume_session` -> thread_store（找出最近的会话、读回记录、判出中断的回合并补记、独占写入）-> 同一个会话标识上的 `start_turn` -> agent_runtime 回合循环 -> model_provider 带上恢复出来的历史 -> thread_store 接着追加 -> CLI 投影

Happy Path:

1. 配置齐全，开发者运行 lime-star，说了一个名字，模型回答。他输入 /exit，进程以 0 结束。
2. 他运行 `lime-star --resume`。终端显示版本号和工作目录，然后一行"已恢复会话 <标识>，已有 1 个回合。"，随后是输入提示。之前的回答没有重放。
3. 他问起那个名字。新进程发给模型的历史里有之前的问答，模型的回答里出现这个名字，回答显示在终端上并写进同一份会话记录。
4. 换一种情形：上一个回合里模型请求写文件，终端出现批准提示时进程被强制结束。运行 `lime-star --resume`，终端多一行"上一个回合没有完成：……当时正在等待批准 write_file，这次操作没有执行。"
5. 没有任何操作被执行，没有批准提示，模型也没有被请求。会话记录里那个回合有了结果和中断结局。他接着对话，模型看得到"没有执行"的那条结果，不会把文件说成已经写好。

Evidence Layers:

- 必须达到: Gate B（两个真实的 lime-star 进程先后在同一个工作目录里运行；模型为回放夹具或显式标注的测试替身）。R9.2-S1 另跑一次 Live（冒烟脚本 `--live`，真实模型）。
- 禁止替代: 只凭直接读取会话记录文件的单元测试冒充新进程恢复；用集成测试里函数的返回值冒充真实进程证据；用回放夹具冒充真实模型。

必跑命令:

| 命令 | 目的 | 状态 |
| --- | --- | --- |
| `uv run pytest tests/unit -q` | 结局的枚举与契约、会话查找、独占写入、读模型、参数解析，不联网 | 通过：包含在全量的 396 条里；三个相关文件单独跑是 22、12、14 条 |
| `uv run pytest tests/integration/test_resume.py -q` | 入口集成：经 app 回合入口的恢复，持久化硬规则的守卫 | 通过：14 条 |
| `uv run pytest tests/integration/test_cli_chat.py tests/integration/test_cli_process.py tests/integration/test_cli_console.py tests/integration/test_cli_resume.py -q` | 交互循环、真实进程、真实控制台 | 通过：30、22、8、6 条 |
| `uv run pytest tests/integration/test_fixture.py -q` | Current fixture：回放驱动完整主链 | 通过：5 条，模型为回放夹具 |
| `uv run python scripts/smoke/resume_gate_b.py` | Gate B 冒烟（模型为回放夹具） | 通过：26 项 |
| `uv run python scripts/smoke/resume_gate_b.py --live` | Live：真实进程加真实模型 | 通过：21 项，glm-5.2 |
| `uv run python scripts/smoke/agent_gate_b.py` | MVP 的冒烟不回归 | 通过：23 项 |
| `uv run pytest tests/integration/test_transcript.py -q` | Gate A：会话记录的事实不回归 | 通过：9 条 |
| `npm run test:contracts` | 契约检查 | 通过：契约 1 项，重新登记之后 |
| `uv run ruff check .` 与 `uv run ruff format --check .` | 静态检查 | 通过 |
| `uv run mypy`，另按 Linux 平台口径跑一次 | 类型检查，含 scripts | 通过：75 个文件 |
| `npm run verify:local -- --full` | 本地门禁 | 通过：签署之后 13 个任务全部通过（2026-11-26） |

未跑的命令在验证矩阵里写明原因和风险。

失败回写: 测试失败时三选一，修产品、修测试、补守卫。本轮的选择记在进度记录里。

完成标准:

- [x] 必跑命令全部有结果记录
- [x] 证据等级达到 Evidence Layers 要求
- [x] 下一刀已写明

## 架构确认

```text
Architecture impact: major
架构图已更新：architecture.md 第 2 节目录地图（app、thread_store、.lime-star 三行）、第 3 节加一条固定判断、本节 7.4
Responsible developer confirmation: 仓库所有者，2026-11-26
确认内容：本阶段不新增目录，也不改依赖矩阵。改变的是业务主链：多了一个入口 resume_session，恢复的进程从 thread_store 读回工作目录下最近的会话，在同一个会话标识上接着写；有开始、没有结局的回合由读取的一方判为中断，把缺的结果和中断结局补进同一份记录，恢复后不自动续跑。协议多一种结局 interrupted。另加一条需求没有写的约束：一个会话记录同一时刻只有一个写入者，靠操作系统在锁文件上的文件锁保证，进程结束时自动释放；没有它，恢复的进程会替一个还活着的回合收尾。替代方案：判定只在读的时候做、不写回记录，模型可见的历史就得在转换时另补一条不在记录里的工具结果，违背"记录的就是交给模型的"；不改结局的枚举、把中断记成取消，以后按结局统计时只能去读原因那一句话。回滚策略：删除 resume_session、thread_store 的 hold、threads、turns 三个模块和 CLI 的 --resume，结局回到四种；已经写出的会话记录不需要迁移，补记的项用的是已有的项类型，只有中断结局的 outcome 值是旧的版本读不懂的。
```

判定为重大的依据是 architecture.md 第 5 节的"改变业务主链"：主链上多了一个入口（恢复），协议多了一种结局。确认块在 architecture.md 第 7 节 7.4 和本计划各有一份，内容相同；仓库所有者于 2026-11-26 回复"确认提交推送"，两处已一起署名，署名用"仓库所有者"，与 P2 到 P4 一致。签署之前，本地门禁停在 Owner 章节的确认块守卫上（396 通过、1 失败），那是"未确认的重大变更不得标记完成"的机械表现；签署之后的结果见验证矩阵的最后一行和进度记录。

## 可追踪验收

按 `../develop/traceable-acceptance.md` 做的一次验收，2026-11-26。阶段是验收：只判断，不顺手改代码。对象是需求 R9 的五条陈述。

### 验收对象

作为开发者，我希望：关掉终端、用 Ctrl+C 打断一个回合，或者进程被强制结束之后，我在同一个目录里运行 `lime-star --resume` 就能接着聊；上一个回合没做完时，它告诉我为什么没做完、有没有执行什么操作，并且不要自己接着跑。这样我才能放心让它在项目目录里动手。

### 主链与证据合同

| 节点 | current owner | 可观测证据 | 通过判据 | 失败分类 |
| --- | --- | --- | --- | --- |
| 1. 找出最近的会话 | thread_store（threads.py） | 终端一行说明里的会话标识；工作目录下的记录文件 | 恢复的是最后有活动的那个，没有另起一份记录 | persistence_gap |
| 2. 读回历史 | thread_store、app | 恢复后第一个请求的消息；read_thread 的结果 | 带着恢复之前的问答，顺序不变，与文件逐项一致 | persistence_gap |
| 3. 判定中断的回合 | thread_store（turns.py）、app | 记录里补上的结果和中断结局；终端上的原因行 | 有开始、没有结局的回合有了结局，原因与记录里的项对得上 | protocol_gap |
| 4. 不续跑 | app | 请求日志的条数；终端上有没有批准提示；磁盘 | 恢复之后、用户输入之前，没有请求，没有提示，文件没有变 | policy_gap |
| 5. 独占写入 | thread_store（hold.py） | 第二个进程的退出码和标准错误 | 原来的进程还开着时，恢复被拒，退出码 1 | policy_gap |
| 6. 接着对话 | agent_runtime、model_provider | 恢复后那个回合的项；终端输出 | 新回合正常完成，写在同一份记录里 | routing_gap |
| 7. 配置重新读取 | app、model_provider | 请求日志里的模型名；缺配置时的退出码 | 用的是新进程自己的配置，缺项时以 2 退出 | routing_gap |

### 跑了哪些真实路径

1. `uv run python scripts/smoke/resume_gate_b.py`：六个真实的 lime-star 进程先后在同一个工作目录里运行，模型为回放夹具，26 项检查通过。
2. `uv run python scripts/smoke/resume_gate_b.py --live`：同样的六个进程，模型是真实的 glm-5.2，21 项检查通过。
3. tests/integration/test_cli_resume.py 的 6 条：真实的进程，批准提示出现之后用 taskkill 结束整棵进程树，新进程带 `--resume`；模型是测试替身。
4. tests/integration/test_cli_console.py 新增的 1 条：隐藏的真实控制台里按真实的 Ctrl+C，之后在新进程里 `--resume`；模型是测试替身。
5. tests/integration/test_resume.py 的 14 条：从 app 回合入口进入，"进程被结束"用 Died 模拟；模型是测试替身。

### 分级结论

用户路径逐步：

| 步骤 | 结论 | 证据位置 | 说明 |
| --- | --- | --- | --- |
| 关掉终端之后 `--resume`，恢复历史并接着聊 | Pass | 冒烟回放里第 1、2 个进程的 6 项检查；Live 冒烟；test_cli_resume.py 的 test_a_new_process_resumes_the_history_and_goes_on | 回放和 Live 里模型都答出了"林小星" |
| 工作目录下有两个会话时恢复最后有活动的那个 | Pass | 冒烟回放与 Live 的同一项检查；test_cli_resume.py 的 test_resume_picks_the_last_session_that_was_active | |
| 等待批准时进程被强制结束；`--resume` 说明上一个回合没有完成、操作没有执行，并且没有续跑 | Pass | 冒烟回放的 7 项检查；Live 冒烟；test_cli_resume.py 的 test_resume_after_the_process_was_killed_at_the_prompt；test_resume.py 的两条 | hi.py 自始至终没有被写 |
| 运行命令时被 Ctrl+C 打断；`--resume` 写明原因是取消 | Pass | test_cli_console.py 的 test_resume_after_ctrl_c_while_a_command_ran_says_it_was_cancelled（真实控制台）；test_cli_chat.py 的 test_resume_shows_the_recap_and_why_the_last_turn_did_not_finish | 冒烟脚本不做这一步：管道驱动发不出真实的 Ctrl+C |
| 恢复后接着问，模型不把没做的操作说成做过 | Pass | 冒烟回放与 Live 的最终回复 | Live 的回答："还没有。上一次我尝试用 write_file 创建 `hi.py`，但在等待你的批准时进程被结束了，操作没有执行，所以文件并没有写入。" |

需求逐条：R9.1、R9.2、R9.3、R9.4、R9.5 都是 Pass，证据见"逐条验证"。

没有到 Pass 的：
- 独占写入在 Linux 上的行为：本机上是 Evidence Gap，CI 通过之后有了状态级的证据。Windows 上有单元、入口集成和真实进程的证据；flock 那一支由 CI 的全量门禁在 Linux runner 上跑过，依据是作业和步骤的状态，日志没有读。
- 已获批准的操作在执行途中被结束之后的恢复，在真实模型上的表现：Evidence Gap。判定本身有单元和入口集成的证据（替身工具），Live 只跑了另一种中断。

### 沉淀的回归资产

| 缺口 | 后续资产 |
| --- | --- |
| 锁的 flock 分支没有本地证据 | CI 的全量门禁（Linux runner）；运行 45798785239 已通过。以后改 hold.py，这一支的证据仍然只能来自 CI |
| 已批准的操作被中断之后，真实模型怎样回答 | 需要时给 resume 场景加一个回合重录；现在只有替身的证据 |
| 真实控制台上批准提示处的 Ctrl+C | 与 P4 留下的是同一个缺口，仍只有进程内的用例；人工验收时可以做一次 |
| "取消的回合要不要让模型知道"仍待决定 | "待仓库所有者决定"第 1 条 |

## 进度记录

每刀一条，按日期追加，不改写历史。

### 2026-11-26

- 改动：产品代码。protocol 的结局加了一种 interrupted；thread_store 新增会话的查找（latest）、回合的读模型（turn_count、last_reason、interrupted）和独占写入（Hold、Busy）；app 新增 resume_session、Recap、NoSession 和 Session.close，打开会话时取独占写入；tool_runtime 的 Registry 多了 dangerous()；CLI 新增 `--resume`，恢复时在横幅之后显示一行概况和未完成的原因，结局 interrupted 有了投影。model_provider 和 agent_runtime 没有改。
- 改动：测试与工具。单元新增 test_thread_store.py；入口集成新增 test_resume.py（持久化硬规则的守卫）、test_cli_resume.py（真实进程）；交互循环、真实进程、真实控制台各补恢复的用例；support.py 多了模拟进程被结束的 Died、等锁放开的 wait_released、用例自己解析记录的两个小工具；回放和录制支持把回合分到几个进程里，新增 resume 场景和夹具 resume.json；回放服务在连接被重置时不再打印堆栈。
- 改动：冒烟与门禁。新增 scripts/smoke/resume_gate_b.py；verify-local 的任务表加了 smoke:resume；两个冒烟脚本共用的小工具挪到 tests/integration/smoke.py；mypy 的检查范围加了 scripts，lint 和 typecheck 由 scripts/smoke/ 的改动触发，CCD-005 清退。
- 改动：规则与文档。根 AGENTS.md 加入持久化硬规则；architecture.md 的目录地图三行、第 3 节第 7 条固定判断、Owner 章节 7.4 与确认块；governance.md 的守卫表、quality-workflow.md 的矩阵各一行；根 README、scripts/README、本目录的 README、技术债追踪。
- 验证：逐项结果见验证矩阵，需求与用例的对应见"逐条验证"，验收结论见"可追踪验收"。门禁停在 7.4 的确认块守卫上，签署之前那是唯一的一条失败。
- 失败回写（修产品，一次）：记录的最后一项读不懂时，latest 抛出的 BrokenItem 起初没有转成 SessionError，命令会把它当成不认识的运行期错误。现在 app 把它转成"工作目录下的会话记录读不懂（哪个文件：什么原因），不能恢复"，退出码 1。
- 失败回写（修测试，产品行为没有为这些失败改动）：
  1. 单元用例两处期望写错：比较"谁最后有活动"的那条用同一个时钟追加项，时间并没有变晚；"最后一项读不懂"的那条坏行缺信封字段，先撞在"信封的字段不对"上。
  2. test_a_thread_has_one_writer_at_a_time 起初没有写下第一项，工作目录里没有可恢复的会话（这是对的），用例补上第一项。
  3. 夹具用例起初假设记录文件按创建顺序排列，它们按名称排序，改成按集合比较。
  4. 冒烟脚本的初版有两处错：一个数据类字段用了可变的默认值，启动即报错；比对补记的结果时写死了调用编号，而真实接口的调用编号不是 call1。前者改成 default_factory，后者改成按内容比对。
- 失败回写（修测试工具）：回放服务在进程被强制结束、连接被重置时往标准错误打印一段堆栈，冒烟的输出里很吵。现在只忽略连接重置和连接中止这两种错误，别的照旧打印。
- 真实接口上看到的事实（glm-5.2，录制 7 次请求，Live 冒烟一次）：
  1. 恢复之后问名字，两次都答出了"林小星"。
  2. 录制时，写 hi.py 的那个回合里模型先说了一句"我来创建这个脚本。"，同一次响应里调用 write_file。所以被中断的回合在记录里是 model_text、tool_call，不是只有调用。
  3. 恢复之后问 hi.py 写好了没有：录制时模型先说"还没有写好。刚才那次写入操作在等待你批准时被结束了，没有执行"，接着列了一次目录再给最终回复；Live 冒烟里它直接回答，没有列目录。两次都没有把文件说成已写好，也没有自己再试一次写入，一次批准提示都没有出现。
  4. 四个问答回合都是一次请求就给出最终回复。
- 观察到但没有处理：
  1. 夹具里每个请求都带着完整的系统指令。resume.json 有 1107 行、43357 个字符，七个请求占了大半。与 P4 的观察相同，夹具再多时可以考虑存的时候去掉系统指令。
  2. 替身模型 FakeModel 的服务线程在进程被结束、连接被重置时也会往测试输出里打印"Exception occurred during processing of request"。它是 P3 以来的噪音，不影响结论；本轮只处理了回放服务的那一份。
  3. latest 要找出最近有活动的会话，读的是每份记录的整个文件（只解析最后一行）。会话很多、很长时再优化，与 P3 的观察第 4 条是同一类。
  4. 刚打开、一项都没写下的会话不会被恢复：工作目录里还没有它的记录，`--resume` 说"没有可恢复的会话"。这是对的，记在这里。
  5. 锁文件在会话结束之后留在 .lime-star/locks 下，每个会话一个空文件，不清理。删它要冒删掉别人刚建好的锁的风险，留着无害。
  6. 录制用进程内模拟的"进程被结束"；真实的强制结束只有 Windows 上 taskkill 的证据，Linux 上是 SIGKILL，由 CI 覆盖。
- 未验证：见验证矩阵后面的"未跑与原因"。
- 完成度：Agent 侧的工作完成。P5 整体 90%，剩下的取决于仓库所有者：确认架构，按路线图 P5 的验收动作核对，对"待仓库所有者决定"答复，说"提交"之后看 CI。
- 下一刀：仓库所有者按路线图 P5 的验收动作核对，回复"确认"之后我把 7.4 的两处确认块署上"仓库所有者"和日期，重跑门禁确认 13 个任务通过；说"提交"再提交，push 要他单独要求。推送之后核对 CI，重点看 Linux 上锁的 flock 分支；通过就在路线图追加 P5 的阶段结论，关闭本计划。

### 2026-11-26（架构确认）

- 改动：仓库所有者回复"确认提交推送"。architecture.md 第 7 节 7.4 和本计划的确认块都已签署，署名用"仓库所有者"，与 P2 到 P4 一致。产品代码和测试没有改。
- 验证：签署之后重跑 `node scripts/verify-local.mjs --full`，13 个任务全部通过，约 4 分钟。test:unit 397 条通过、3 条跳过（Live）；smoke:gate-b 23 项；smoke:resume 26 项；test:guards 41 条；architecture 21 条。
- "待仓库所有者决定"的两条：这次的回复没有提到它们，都保持现状，不改代码。
- 完成度：95%。代码、验证和架构确认都有了；还差 CI。
### 2026-11-26（提交与 CI）

- 改动：仓库所有者说"确认提交推送"。提交 033df27，42 个文件，已推送到 origin/main；路线图追加 P5 的阶段结论，验证矩阵的 P5 行补上结果，当前结论更新为 85%；本计划关闭，从本目录 README 的当前计划表里删掉这一行。
- 验证：推送之后 CI 运行 45798785239，针对提交 033df27，结论 success；verify 作业的每一步都成功，Local gate (full) 在 Linux runner 上通过，约 2 分钟。这是恢复的代码、锁的 flock 分支和恢复的冒烟第一次在 Windows 以外运行。依据是运行、作业和步骤的状态，日志没有读。记录的这一次提交只改文档，不再为本计划追记它的 CI。
- 未跑：见验证矩阵后面的"未跑与原因"，剩下的都不是退出条件。
- "待仓库所有者决定"的两条：仍待答复，带到路线图的下一刀里。
- 完成度：P5 100%。路线图 85%，P0 到 P3 和 P5 完成，P4 已交付，P6、P7 未开始。
- 下一刀：见路线图 2026-11-26 P5 resume 完成那一条。

## 当前结论

- 治理四分类：current 新增 thread_store 的 hold.py（Hold、Busy）、threads.py（latest）、turns.py（turn_count、last_reason、interrupted）；app 的 resume_session、Recap、NoSession 和 Session.close；CLI 的 `--resume` 与恢复时的说明；protocol 的 Outcome.INTERRUPTED；tool_runtime 的 Registry.dangerous；scripts/smoke/resume_gate_b.py 和 verify-local 的 smoke:resume 任务；测试里的 Died、smoke.py、分段录制的录制脚本和 resume 夹具。current 扩展：Session 持有独占写入；chat 的 recap 参数和 interrupted 的投影；thread-items 契约的结局枚举；pyproject 的 mypy 范围和 verify-local 里 lint、typecheck 的触发路径；support.py 里共用的小工具。compat、deprecated、dead 均无新增或删除。直接替换掉的内部做法不属于四类：test_help_does_not_list_resume_yet 由 test_help_lists_resume 取代；agent_gate_b.py 里的四个小工具挪进 tests/integration/smoke.py；录制场景从"一段回合"改成"若干段"。
- 验证结果与未验证原因：见验证矩阵。路线图 P5 的四条退出条件逐条有结果：交付的需求逐条有验证记录；`--resume` 在新进程里恢复历史并继续对话；Ctrl+C 打断和强制结束两种情形下，回合分别被记为取消和被判为中断，恢复后不自动续跑；两种恢复都有真实进程的 Gate B 证据，真实控制台上的 Ctrl+C 另有一条。可追踪验收里 R9 的五条都是 Pass。未验证：真实控制台上批准提示处的 Ctrl+C；已批准的操作被中断之后在真实模型上的表现；Linux 上逐条用例的结果（CI 的日志没有读，只有作业和步骤的状态）。架构确认块已由仓库所有者于 2026-11-26 签署，本地门禁 13 个任务全部通过，CI 通过（运行 45798785239）。
- 未做与原因：路线图已在提交 033df27 推送、CI 通过之后追加 P5 的阶段结论，本计划关闭。P4 仍记为"已交付，等答复"，p4 的计划还开着：P4 的两件事和"取消的回合要不要让模型知道"都还等仓库所有者答复，带在路线图的下一刀里。
- 来源声明：对照阅读了 lime 仓库 lime-rs/crates/thread-store 的目录结构，lib.rs 与 store.rs 的文件头，history/replay.rs，history_validation.rs（读过，没有取用），runtime_snapshot.rs 的文件头，以及 internal/aiprompts/query-loop.md 里关于恢复路径的条目。取三个思路：会话放在哪里、怎样列出和读回是存储自己的事，调用方只拿到会话标识和项；判定只从已落盘的项出发，每次重新读文件来算，补记只写缺的那几项；恢复后的对话沿用从同一份会话记录派生的上下文，不另拼一份。按本仓库语境重写，没有复制原文。Windows 上 msvcrt.locking 的行为是本机用临时脚本实测的，脚本在仓库外，事后已经删掉。真实模型只用于录制夹具（7 次请求）和一次 Live 冒烟。

完成度: 100%
