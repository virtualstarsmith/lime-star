# p1-chat 计划

状态: done
日期: 2026-11-24
主目标: 接上 OpenAI 兼容模型，做出多轮对话命令，并让每次模型请求都留下可关联的记录。

## 目标

配置齐全时，不带参数运行 `lime-star` 开始会话，连续对话多轮后模型仍记得前面的内容；每次模型请求在 `.lime-star/logs/` 下追加一条不含内容的记录；缺少配置时以退出码 2 拒绝启动并点名变量；密钥不出现在终端输出和日志里；回合出错或被 Ctrl+C 取消后，会话都能继续。凭证规则与守卫在同一批落地。

## 当前事实

- 仓库所有者于 2026-11-24 说"开始p1"。开工前检索未决项（`rg "^未决 OQ-" internal/prd`），没有命中。路线图 P1 交付的需求编号和证据等级见 `../roadmap/agent-practice.md`，这里不复述。
- 本机没有设置 LIME_STAR_BASE_URL、LIME_STAR_API_KEY、LIME_STAR_MODEL，工作目录里也没有 `.env`。Agent 手上没有真实密钥，所以 Live 证据（真实模型连续对话三轮）本轮拿不到，要等仓库所有者提供凭证后补做。替身或回放不得冒充 Live。后续：仓库所有者于当日在仓库根配置了 `.env`，Live 已补做，见进度记录。
- 目录地图里 `src/lime_star/app/`、`src/lime_star/model_provider/`、`.lime-star/` 三项登记为"路线图 P1"。cli 现在只有参数处理，不带参数按用法错误处理，这是 P0 留下的过渡行为。
- 运行时不依赖第三方包，模型 SDK 随本阶段加入。verify-local 任务表有 8 个任务。scripts 冻结基线是根文件 6 个，没有一级目录。
- 技术债 CCD-001 的前提（tests/）已由 P0 建立，路线图建议并入本计划。CCD-002 要在首次追加 Owner 章节之前补，CCD-003 要在 agent_runtime 落地之前补，两条最早都落在 P2，本计划不扩大到它们。
- 本机环境：uv 0.12.4、Python 3.14.5、Node 25.2.1、Windows PowerShell 5.1；没有设置代理环境变量。
- 动手前确认的两个 Windows 事实，决定了下面的设计：
  - 阻塞中的网络读取在 Windows 上不保证被 Ctrl+C 打断。所以模型请求放在工作线程里，主线程只等待一个可被打断的事件。
  - CPython 的控制台读取（Modules/_io/winconsoleio.c，3.14 分支的 read_console）被 Ctrl+C 打断后会重新读取，在非主线程里不抛异常。所以标准输入可以由后台线程持续读取；回合进行中到达的行进入队列，回合结束时丢弃并计数（R13.8、R13.9，决策 D-06）。
- lime 对照阅读（只读）：lime 仓库 internal/aiprompts/prompt-foundation.md，以及 lime-rs/crates/model-provider 目录的结构。看到的点：基础指令只有一个组装者，前端不生成提示词，模型边界只把同一份指令转成接口表达；请求传输、错误归类、流解析、历史各占一个文件，这个 crate 只处理与模型接口有关的事。本计划据此把系统指令的来源收在 model_provider 的一个模块里，并让请求、错误归类、请求日志各自独立。

## 写集与避让

### 本轮认领写集

新建：

- `src/lime_star/app/__init__.py`、`src/lime_star/app/session.py`
- `src/lime_star/model_provider/__init__.py`、`config.py`、`client.py`、`prompt.py`、`errors.py`、`request_log.py`、`provider.py`
- `src/lime_star/cli/chat.py`
- `tests/unit/test_config.py`、`tests/unit/test_env_example.py`、`tests/unit/test_errors.py`、`tests/unit/test_request_log.py`
- `tests/integration/conftest.py`、`tests/integration/support.py`、`tests/integration/fake_model.py`
- `tests/integration/test_turn.py`、`tests/integration/test_cli_chat.py`
-	ests/integration/console_host.py、	ests/integration/test_cli_console.py（验证中途追加：真实控制台下的 Ctrl+C 证据）
- `tests/integration/test_live.py`（验证中途追加：Live 用例，默认跳过，设置 `LIME_STAR_LIVE=1` 才运行）
- `tests/integration/test_guard_secrets.py`、`tests/integration/test_guard_doc_links.py`
- `.env.example`
- `scripts/security/check-secrets.mjs`
- 本计划

修改：

- `pyproject.toml`、`uv.lock`：加入模型 SDK，锁文件由 uv 生成。
- `src/lime_star/cli/main.py`：去掉不带参数报用法错误的过渡行为，接入会话。
- `tests/integration/test_cli_process.py`：新增进程用例，删除过渡用例。
- `scripts/verify-local.mjs`：任务表新增 secrets 和 test:guards。
- `governance/scripts-baseline.json`：由 `--update` 生成，登记一级目录 security。理由：路线图 P1 的新增脚本按规则必须进入领域目录，密钥守卫是第一个 security 脚本。
- 根 `AGENTS.md`：凭证硬规则与守卫，高频命令。
- `internal/aiprompts/architecture.md`：app、model_provider、.lime-star 三行的状态列。
- `scripts/README.md`、根 `README.md`、`README.md`（本目录）。
- `tech-debt-tracker.md`：CCD-001 清退。

### 只读避让写集

- `../roadmap/agent-practice.md`：路线图规定它是只读避让集，阶段结论等仓库所有者验收后再追加。
- `../prd/`：需求已确认，不改。
- `src/lime_star/protocol/`、`agent_runtime/`、`tool_runtime/`、`thread_store/`、`protocol/`：属于 P2、P3，落地前不创建。P1 的会话历史只放在 app 的内存里，不落盘；P3 建立 thread_store 时直接替换。
- scripts 下其余脚本，governance 下其余基线。
- `.github/workflows/quality.yml`：门禁经 verify-local 运行，不需要改。

## 删除集

- `src/lime_star/cli/main.py` 里"不带参数按用法错误处理"的过渡行为，以及对应的用例 `test_bare_command_is_a_usage_error_for_now`。该用例自己注明由 R13.1 取代。

## 本阶段的默认选择

1. P1 的一个回合只发一次模型请求。循环和工具属于 P2，start_turn 不预建循环。R3.1-S1"一个回合三次请求"因此在模型边界上验证：同一 turn_id 连续三次请求得到三条记录。
2. 请求不流式。决策 D-07 不承诺逐字显示，非流式响应直接带 token 用量，少一个解析面。
3. 模型请求放在工作线程，主线程等待。落选的备选：主线程直接调用 SDK，Windows 上阻塞读不保证被 Ctrl+C 打断。
4. 标准输入由后台线程持续读取。落选的备选：回合结束时用非阻塞读清空输入，Windows 上管道和控制台各要一套系统调用。
5. 会话记录在 P1 是内存里的消息与回合结局，经 read_thread 读取。落选的备选：现在就写成 JSONL，那是 P3 的 thread_store，会提前出现第二份事实源。
6. SDK 关闭自动重试（max_retries=0），落实决策 D-11。超时沿用 SDK 的默认值：连接 5 秒，读 600 秒。落选的备选：把读超时压到 120 秒，推理模型的长输出会被误判为失败；做成可配置，扩大配置面。
7. 出错时只显示错误类别和接口状态码，不显示 SDK 的异常文本；未预料的异常只显示类名。理由：异常文本可能带请求详情（R3.3、R4.3-S2）。
8. 配置校验：密钥只允许不含空白的可打印 ASCII，地址必须是 http 或 https。不合法的值以退出码 2 拒绝，并且不回显值。理由：不合法的值会让 SDK 抛出带请求头的异常。
9. 测试里的模型是本地替身服务：走真实 HTTP，按 OpenAI 响应的形状返回脚本化的响应，没有从真实运行录制。所有相关证据都标注"模型为测试替身"。
10. 密钥守卫在 verify-local 里恒跑，因为密钥可能出现在任何文件里。
11. CCD-001 的回归用例放在 tests/integration（它们启动真实的脚本进程）；verify-local 新增任务 test:guards，由 scripts/ 的改动触发。
12. 等待用 0.1 秒的短切片（验证中途追加）。真实的 Ctrl+C 在 Windows 上靠 CPython 的一个事件唤醒主线程，但这个事件只在真正的信号处理函数里置位，解释器版本之间也不一致；挂起的中断则一定会在下一次字节码边界被处理。切片只决定中断最多晚多久生效，不影响回复的延迟。落选的备选：60 秒的长切片，中断可能被拖到请求结束。
13. 输入结束或读不下去是永久状态（验证中途追加）。落选的备选：结束信号只在队列里出现一次，之后再取输入会永远等下去。
14. 真实控制台的用例只在 Windows 上运行（验证中途追加）：在隐藏的新控制台里启动进程，由同一控制台里的宿主进程投递按键，并用 GenerateConsoleCtrlEvent 发出真实的 Ctrl+C。落选的备选：用 WriteConsoleInput 投递 Ctrl+C 按键，实测在隐藏控制台里不产生事件。

## 阶段与退出条件

### A 配置与凭证守卫

- 退出条件：R4.1 到 R4.6 的场景各有通过的用例；`.env.example` 只含三个变量和占位值；`scripts/security/check-secrets.mjs` 在本仓库通过，在放了密钥样例的临时仓库里报错并非零退出；冻结基线登记 security；verify-local 在任何改动下都选中 secrets。

### B 模型边界

- 退出条件：从 app 回合入口驱动时，请求日志的每条记录含 R3.1 列出的全部字段，失败只记类别和状态码（R3.1 到 R3.3）；同一会话各次请求的系统指令逐字相同（R2.2）；鉴权错误与上下文超限各归为一类，并且不重试（R12.4、决策 D-11）；取消后主线程不再等待、结局为取消，下一个回合带上之前的历史（R12.5-S2、R12.6-S1）。

### C 回合入口与终端交互

- 退出条件：R13.1 到 R13.13 的场景在真实进程或交互循环里有通过的用例，其中 Ctrl+C 的两条（R13.11、R13.12）用模拟中断；缺少配置时以 2 退出、点名变量、不发请求（R4.2）；标准输出、标准错误和请求日志里都搜不到密钥（R4.3）。

### D 收尾

- 退出条件：`npm run verify:local -- --full` 通过；AGENTS.md、architecture.md、两个 README 同步；架构确认块备好，等仓库所有者确认；路线图 P1 的四条退出条件逐条有结果，Live 写明未跑和补做的办法。

### E 技术债 CCD-001

- 退出条件：check-doc-links 有仓库内的回归用例，证明带目录的错误路径会报违规、裸文件名可以全树查找；改动 scripts/ 时 verify-local 会执行它；技术债表里 CCD-001 标为 closed。

## 验证矩阵

| 阶段 | 命令 | 证据等级 | 结果 |
| --- | --- | --- | --- |
| A | `uv run pytest tests/unit/test_config.py tests/unit/test_env_example.py -q` | Unit | 通过：22 条。配置来源、缺项点名、不合法的值不回显、`.env.example` 只有占位值 |
| A | `uv run pytest tests/integration/test_guard_secrets.py -q`；`node scripts/security/check-secrets.mjs` | 守卫（真实脚本进程） | 通过：12 条，覆盖 R4.5-S1 和 R4.6-S1 的五种密钥格式。守卫在本仓库通过；用临时索引把本轮新文件一并纳入后，扫描 86 个文件也通过 |
| B | `uv run pytest tests/unit/test_errors.py tests/unit/test_request_log.py -q` | Unit | 通过：20 条 |
| B、C | `uv run pytest tests/integration/test_turn.py -q` | 入口集成（模型为测试替身） | 通过：12 条 |
| C | `uv run pytest tests/integration/test_cli_chat.py -q` | 入口集成（交互循环，Ctrl+C 为模拟中断） | 通过：13 条 |
| C | `uv run pytest tests/integration/test_cli_process.py -q` | Gate B（真实进程、管道输入，模型为测试替身） | 通过：16 条，其中 5 条是 P0 的 |
| C | `uv run pytest tests/integration/test_cli_console.py -q` | Gate B（真实进程、真实控制台、真实 Ctrl+C 事件，模型为测试替身） | 通过：5 条，只在 Windows 上运行；取消在 30 毫秒左右生效；每条用例收尾时都确认会话进程已经结束 |
| P1 | `LIME_STAR_LIVE=1 uv run pytest tests/integration/test_live.py -s -v`，模型是仓库所有者配置的真实模型（glm-5.2） | Live 加 Gate B（真实进程、真实模型） | 通过：三轮对话里第三轮答出第一轮说的名字；三次请求各有一条状态为 ok 的记录，token 用量来自真实接口（输入 205、220、235，输出 20、30、30）；日志里没有消息内容和密钥；标准错误为空 |
| P1 | 同一命令里的鉴权用例：用无效密钥请求真实接口一次 | Live（负向） | 通过：真实接口返回 401，终端说明"鉴权失败（HTTP 401）"，日志记录类别 auth、状态码 401；随后正常退出，退出码 0；真实密钥没有被发送，也没有出现在任何输出里 |
| P1 | 真实控制台加真实模型的 Ctrl+C，仓库外的一次性检查，不进测试集 | Live 加 Gate B | 通过两次：请求在途时发出 Ctrl+C，0.02 秒出现"已取消。"并回到提示；同一会话继续提问得到回答；退出码 0 |
| P1 | `npm.cmd run verify:local -- --full` | 门禁 | 通过：最后一次在交付的工作树上跑，10 个任务，退出码 0，用时 96.8 秒；test:unit 里 117 条通过、2 条跳过，跳过的是默认不运行的 Live 用例，所以门禁不会调用真实接口。secrets 任务此时扫的是已跟踪的 63 个文件，本轮新文件要等提交后才在它的范围内，所以另用临时索引扫过一次 |
| E | `uv run pytest tests/integration/test_guard_doc_links.py -q` | 守卫（真实脚本进程） | 通过：8 条 |
| 全程 | `uv run pytest -q` 连跑三遍 | 汇总 | 三遍都是 115 条通过，各约 68 秒；当时还没有 `test_env_example.py` 的那一条 |
| 全程 | `node scripts/verify-local.mjs --dry-run` 配各组路径 | 门禁（任务选择） | 通过：改 scripts/ 下的脚本选中 scripts-baseline、secrets、test:guards；secrets 恒跑；`--full` 选中 10 个任务，lock 排在其余 Python 任务之前 |
| 全程 | `uv run mypy` 与 `uv run mypy --platform linux` | 类型检查 | 通过 |
| 全程 | `npm run test:contracts` | 契约检查 | 未跑：本轮没有改协议、契约或 schema |

## 验证合同

预算标签: budget:normal（定向测试加门禁）

主链: CLI 输入 -> app 回合入口 start_turn -> model_provider -> .lime-star/logs 的请求日志 -> CLI 投影

Happy Path:

1. 三个配置变量齐全（环境变量，或工作目录下的 `.env`），不带参数运行 `lime-star`。
2. 终端显示版本号和工作目录，随后出现输入提示。
3. 用户输入一行文字。app 记下用户消息，model_provider 带上系统指令和到此刻为止的全部历史，发起一次请求。
4. 请求日志追加一条含 R3.1 字段的记录；终端显示模型的回复；回到输入提示。
5. 用户输入 `/exit`，或按 Ctrl+C，或关闭输入，进程以 0 退出。

Evidence Layers:

- 必须达到: Live（真实模型连续三轮，R2.1-S1）加 Gate B（真实 CLI 进程）。过程证据用入口集成，从 open_session 和 start_turn 进入。
- 禁止替代: 替身或回放的对话冒充真实模型通过；单元测试冒充 Gate B；模拟中断冒充真实控制台上的 Ctrl+C，后者按入口集成报告。

必跑命令:

| 命令 | 目的 | 状态 |
| --- | --- | --- |
| `uv run pytest tests/unit -q` | 配置、错误归类、请求日志的纯逻辑 | 通过：51 条 |
| `uv run pytest tests/integration/test_turn.py -q` | 入口集成：历史、系统指令、日志、出错、取消 | 通过：12 条 |
| `uv run pytest tests/integration/test_cli_process.py tests/integration/test_cli_chat.py -q` | Gate B（管道输入）与交互循环 | 通过：29 条 |
| `uv run pytest tests/integration/test_cli_console.py -q` | Gate B（真实控制台与 Ctrl+C 事件） | 通过：5 条，只在 Windows 上运行 |
| `uv run pytest tests/integration -q -k test_guard_` | 守卫脚本的回归（R4.6、CCD-001） | 通过：20 条 |
| `node scripts/security/check-secrets.mjs` | 密钥守卫（R4.5、R4.6） | 通过 |
| `LIME_STAR_LIVE=1 uv run pytest tests/integration/test_live.py -s -v` | Live（R2.1-S1、R12.4-S1）加 Gate B（真实模型） | 通过：2 条，用时 14 秒 |
| `npm.cmd run verify:local -- --full` | 本地门禁 | 通过：10 个任务，退出码 0 |

必跑命令都已跑过。Live 由 Agent 用仓库所有者在仓库根配置的 `.env` 跑：Agent 没有读取或输出密钥，只核对了变量名、是否设置，以及模型名和接口的主机名。真实接口的响应形状、错误格式和 token 用量字段由此对过：SDK 正常解析了真实响应，`usage` 的三个字段都有值，错误的密钥返回 401。

失败回写: 测试失败时三选一，修产品、修测试、补守卫。本轮的记录：

- 修产品。入口集成的取消用例发现主线程等了 30 秒才取消：等待用了 60 秒的切片，而挂起的中断只能在字节码边界被处理。查 CPython 源码后确认，真实的 Ctrl+C 在 Windows 上靠一个事件唤醒主线程，但事件只在真正的信号处理函数里置位，解释器版本之间也不一致。等待改成 0.1 秒的切片。
- 修产品。输入结束之后再取输入会永远等下去，因为结束信号只在队列里出现一次。改成永久状态。
- 修产品。标准输入的入参从 `TextIO` 改成只要求 `readline` 的最小接口，测试不必为了凑类型去继承 `StringIO`。
- 补守卫。密钥守卫的通用规则原先要求关键字前面有词边界，漏掉了 `MY_TOKEN = "..."` 这类下划线命名；回归用例抓到后修正。
- 修测试和夹具，产品行为没有为这些失败改动：标识生成器每次调用都新建；假设了晚到的日志记录排在前面；临时目录没建父目录；"不回显"的断言对示例地址过严；期望的提示个数数错；管道夹具的解码器把完整的字节也扣下、换行没有归一化；夹具和用例漏导入；控制台用例到标准输出里等一条写进标准错误的提示；消息列表把系统指令也算了进去。
- ruff 与 mypy 报出的问题都按修产品处理：`cli/chat.py` 漏了两个导入，`RequestLog` 需要延迟标注，一处变量标注让两种消息类型冲突，枚举应继承 `StrEnum`，系统指令有一行超宽。

完成标准:

- [x] 必跑命令全部有结果记录
- [x] 证据等级达到 Evidence Layers 要求：Gate B 与 Live 都已达到
- [x] 下一刀已写明

## 架构确认

```text
Architecture impact: major
架构图已更新：architecture.md 第 2 节目录地图（app、model_provider、.lime-star 三行的状态列）
Responsible developer confirmation: 仓库所有者，2026-11-24
确认内容：本阶段落地 app 回合入口和 model_provider 两个 owner，第一次引入模型 HTTP transport 和请求日志持久化，CLI 输入由此第一次贯通到模型再回到终端。替代方案：让 CLI 直接调用模型 SDK，被 architecture.md 第 4 节禁止；现在就把会话历史落盘，那是 P3 的 thread_store，会提前出现第二份事实源。回滚策略：删除 app 与 model_provider 两个目录和模型 SDK 依赖，cli/main.py 回到不带参数报用法错误；请求日志在 .lime-star/ 下，不入库。
```

判定为重大的依据是 architecture.md 第 5 节的"引入新的持久化或 transport"。P1 不追加 Owner 章节，路线图把它排在 P2 起。仓库所有者于 2026-11-24 回复"架构确认"；署名沿用需求确认时的写法，见 `../prd/agent-practice.md` 开头的状态行。

## 进度记录

每刀一条，按日期追加，不改写历史。

### 2026-11-24

- 改动：模型边界 `src/lime_star/model_provider/`（配置、客户端、系统指令、错误归类、请求日志、Provider）；app 回合入口 `src/lime_star/app/`；CLI 的会话交互 `src/lime_star/cli/chat.py`，`cli/main.py` 接入会话并删掉不带参数报用法错误的过渡行为。`.env.example`。密钥守卫 `scripts/security/check-secrets.mjs`，冻结基线登记 security，verify-local 新增 secrets 与 test:guards。根 AGENTS.md 的凭证硬规则与高频命令；architecture.md 三行状态；scripts/README、根 README、本目录的 README；技术债 CCD-001 清退。依赖：运行时 openai 3.58.0，开发 httpx2 2.16.2，锁文件由 uv 生成。
- 改动（验证中途追加）：`tests/integration/support.py`（共用的客户端、日志读取、子进程环境）；`tests/integration/console_host.py` 与 `tests/integration/test_cli_console.py`（真实控制台下的 Ctrl+C 证据）；`tests/unit/test_env_example.py`。
- 验证：逐项结果见验证矩阵。失败回写见验证合同。
- 真实控制台的对照实验在仓库外用原型做，结论落成了用例：
  - 用 WriteConsoleInput 投递 Ctrl+C 按键，在隐藏控制台里不产生事件，连一个最小探针都收不到，所以这种投递不能用。
  - 用 GenerateConsoleCtrlEvent 发出事件：产品在 30 毫秒左右取消回合并回到提示，后台的标准输入读取线程继续交付输入，随后退出码为 0。
  - 一个后台线程阻塞在 `sys.stdin.buffer` 上时，解释器收尾会报致命错误 `_enter_buffered_busy`，原型宿主进程就撞上了。产品经由 `sys.stdin` 文本流读取并一直持有它，这个流不会被关闭；已在代码里写明，进程用例的退出码断言守着它。
  - 原型运行期间没有启动任何 Windows Terminal 或 OpenConsole 进程，隐藏控制台没有弹出窗口。
- 观察到但没有处理：
  - 回合被取消后，如果用户立刻退出，被放弃的那次请求可能晚于进程结束才返回，于是没有请求记录。P1 不处理。
  - 设置了系统代理的环境里，指向回环地址的模型接口也会走代理，因为 SDK 读环境里的代理设置。P1 不处理；测试里用 NO_PROXY 和不读代理的客户端绕开。
  - 系统临时目录里留着原型实验的文件：`ls-console-proto` 目录，以及 26 个同时含 out.log 与 err.log 的 `tmp*` 目录。清理命令被执行策略拦截，没有绕过。
- 未验证：
  - Live（R2.1-S1）：Agent 没有真实密钥。真实接口的响应形状、错误格式和 token 用量字段都没有对过。
  - R2.1-S2（上一个回合里有两次工具调用）：P1 没有工具，场景不成立，随 P3 的夹具驱动 start_turn 验证。
  - R12.5-S1（终止正在运行的命令）：命令执行属于 P4。
  - R13.11、R13.12 由人在真实终端窗口里按键：用例投递的是同一种控制台事件，但没有经过键盘和终端窗口。
  - Windows 以外的平台：本地只在 Windows 上验证。控制台用例在别的平台上跳过；进程用例在那边的收尾行为没有跑过。mypy 按 Linux 平台口径检查通过。
  - Python 3.11 到 3.13：没有安装。短切片的等待不依赖 3.14 的唤醒机制，但没有实测。
- 完成度：90%。Agent 侧的实现、本地验证、规则与文档同步已完成，剩余取决于仓库所有者。
- 下一刀：仓库所有者把地址、密钥、模型名放进 `.env` 或环境变量，亲手用 `lime-star` 对话三轮并核对请求日志，再按路线图 P1 的验收动作逐条核对，确认架构确认块；验收后说"提交"。CCD-002、CCD-003 在 P2 开工前补。

### 2026-11-24（补：控制台用例的收尾）

- 起因：第一轮控制台用例失败之后，夹具的收尾只结束了宿主进程。被测的会话进程是宿主的子进程，它活了下来，在隐藏控制台里一直等输入。核对遗留进程时发现，已手动结束。
- 改动：`tests/integration/console_host.py` 把被测进程放进一个随宿主结束而关闭的作业；命令管道关闭时主动结束被测进程；把被测进程的进程号报告给调用方。`tests/integration/test_cli_console.py` 的收尾改为先让宿主正常收尾，再凭进程句柄确认被测进程已经结束，确认不了就让用例失败。新增用例 `test_closing_a_stuck_session_ends_the_process`。
- 验证：控制台用例连跑两遍都是 5 条通过，每遍之后没有残留的 lime-star.exe。另用仓库外的脚本验证兜底：回合卡在等待模型时强杀宿主，收尾在 0.01 秒内确认会话进程已经结束。
- 改动：`model_provider/provider.py` 里 complete() 的文档改准确。进程若在迟到的响应之前退出，那次请求不会有记录。
- 验证：最终工作树上的全量门禁见验证矩阵，门禁之后没有遗留进程。
- 完成度：90%，不变。

### 2026-11-24（补：Live）

- 起因：仓库所有者在仓库根配置了 `.env`（三个变量齐全，被 Git 忽略、未被跟踪），并要求开始真实测试。Agent 没有读取或输出密钥，只核对了变量名、是否设置，以及模型名和接口的主机名。
- 改动：新增 `tests/integration/test_live.py`。它默认跳过，设置 `LIME_STAR_LIVE=1` 才运行。配置经产品自己的 load_config 取得，只以环境变量传给在临时目录里运行的子进程。断言不直接比较密钥：pytest 的失败信息会回显参与比较的值，所以先算出不带值的布尔结果再断言，并在打印任何子进程输出之前先做密钥检查。
- 改动：为了让 Live 用例复用管道夹具，把 `CliProcess`、`run_lime_star`、`PROMPT` 挪到 `tests/integration/support.py`，把 `start_cli` 夹具挪到 `tests/integration/conftest.py`。搬移后管道用例和控制台用例照常通过（21 条），Live 用例在不设开关时跳过（2 条）。
- 验证：逐项结果见验证矩阵。Live 2 条通过。另在仓库外用真实控制台对真实模型做了两次 Ctrl+C 的一次性检查，都通过。
- 观察到但没有处理（新增）：
  - 取消之后的回合里，模型会把被取消的那条消息一起回答。实测取消一次"写 1500 字短文"之后问"一加一等于几"，模型先补写了整篇短文，再回答 2，用了 37 秒。原因是 R12.6 要求带上取消之前的历史，而 P1 没有把"那个回合被取消"告诉模型。这需要仓库所有者决定：保持现状；或者在会话记录里记下回合结局并让模型看到，这涉及 R6.4，建议在 P2、P3 设计模型可见的历史之前定。
  - 被取消的请求在接口那边仍会跑完并计费，实测一次 2484 个输出 token。进程若在它返回之前退出，日志里就没有这次请求的记录。
  - 回复不流式，长回复期间终端没有输出，实测最长等了 37 秒。决策 D-07 把逐字显示留到 MVP 之后。
- 未验证（在原有条目之外新增一条）：上下文超限（R12.4-S2）没有在真实接口上触发，需要很长的输入，费用高；归类逻辑只在构造的异常上验证过。
- 完成度：95%。路线图 P1 的四条退出条件都有结果。剩余取决于仓库所有者：亲手做验收动作，确认架构确认块，然后说"提交"。

### 2026-11-24（提交）

- 改动：仓库所有者说"提交"。执行 commit，不推送。本条随本轮改动一并入库。
- 本计划的状态保持 in_progress，原因有两个：架构确认块还等仓库所有者签字；CI 要等推送之后才能核对。
- 完成度：95%，不变。
- 下一刀：仓库所有者确认架构确认块；要求 push 之后核对 CI；通过后在路线图的进度记录里追加 P1 的阶段结论，把本计划标为 done，并从 `README.md` 的当前计划表移除。

### 2026-11-24（架构确认）

- 改动：仓库所有者回复"架构确认"。架构确认块已填写，署名用"仓库所有者"，与需求确认时的写法一致。
- 验证：只改了文档。改完后文档链接守卫和行数守卫通过。
- 完成度：95%。还差 CI：仓库所有者同时要求 push，推送之后核对。
- 下一刀：推送，核对 CI；通过后在路线图的进度记录里追加 P1 的阶段结论，把本计划标为 done。

### 2026-11-24（推送、CI 与收尾）

- 改动：仓库所有者要求 push。推送到 origin/main，快进 c2845c1..579eb2b，共两个提交：65fb7bf 是 P1 的实现，579eb2b 是架构确认。
- 验证：CI 首次运行即通过：运行 45341894974，结论 success，ubuntu-latest，从创建到结束约 50 秒。作业 verify 的各步骤都成功，其中包括在 Linux 上跑的全量门禁。依据是运行和步骤的状态，日志接口返回 403，没有读。所以 Linux 上实际跑了多少条、跳过多少条没有直接看到；按设计，控制台用例和 Live 用例在 Linux 上跳过。
- 改动：路线图追加 P1 的阶段结论，验证矩阵的 P1 行改为通过，当前事实与完成度同步。本计划状态改为 done，并从 `README.md` 的当前计划表移除。计划文件保留，因为路线图的进度记录引用它。本条所在的提交在写入时还没有推送，等仓库所有者要求。
- 未验证：Windows 以外的平台只有 CI 这一次运行作为证据；Python 3.11 到 3.13 仍然没有跑过。
- 完成度：100%。路线图 P1 的四条退出条件全部满足，架构变更已确认，CI 通过。
- 下一刀：按路线图 P2 的开工话术开始 P2。开工前先定"取消之后的回合要不要把结局告诉模型"；CCD-002、CCD-003 在 P2 开工前补。

## 当前结论

- 治理四分类：current 新增 app 回合入口（open_session，Session 的 start_turn 与 read_thread）；model_provider（配置、客户端、系统指令、错误归类、请求日志、Provider）；CLI 的会话交互 chat；密钥守卫 scripts/security/check-secrets.mjs；verify-local 的 secrets 与 test:guards 两个任务；守卫脚本的回归用例。compat、deprecated、dead 均无新增或删除。删掉的只有 cli/main.py 里"不带参数报用法错误"的过渡行为，它没有需求编号，不属于四类中的任何一类。
- 验证结果与未验证原因：见验证矩阵与进度记录。路线图 P1 的四条退出条件都已满足：逐条验证、Live（真实模型连续三轮）、Gate B、密钥守卫。架构变更已由仓库所有者确认，推送后 CI 通过。剩余的未验证项不阻塞这四条，见进度记录。
- 来源声明：对照阅读了 lime 仓库 internal/aiprompts/prompt-foundation.md，以及 lime-rs/crates/model-provider 目录（lib.rs、http.rs、Cargo.toml 和目录结构）。只取两个做法：基础指令只有一个组装者；请求传输、错误归类、历史各占一个模块。按本仓库语境使用，没有复制原文。另读了 CPython 3.14 分支的 Modules/_io/winconsoleio.c、Python/parking_lot.c、Modules/signalmodule.c，用来确认 Windows 上 Ctrl+C 唤醒主线程和控制台读取的机制。

完成度: 100%
