# p0-bootstrap 计划

状态: in_progress
日期: 2026-11-24
主目标: 建立 Python 工程骨架和 lime-star 空命令，让本地门禁从第一天起就覆盖 Python 代码。

## 目标

干净克隆上执行 `uv sync` 之后，`uv run lime-star --version` 可用，`--help` 与未知参数按需求表现；verify:local 的任务表里有 lint、typecheck、test:unit、lock 四个 Python 任务，改动 Python 代码、依赖声明或锁文件就会触发。成功之后，后续每个阶段写下的第一行 Python 代码都已经在门禁之内。

## 当前事实

- 仓库所有者于 2026-11-24 确认需求并已提交，main 领先 origin/main 一个提交，尚未推送。路线图 P0 交付 R1.1 到 R1.4，需求正文在 `../prd/agent-practice/cli.md`；开工前检索未决项，没有命中。
- 目录地图里 `src/lime_star/cli/`、`tests/` 和依赖三件套登记为"路线图 P0"。本阶段只把这三行的状态改为"已有"，不新增 owner。
- verify-local 的任务表里 Python 任务还是两行注释占位。scripts 根目录受冻结基线保护，本轮只改既有脚本的正文，不新增脚本，不改基线。
- CI 工作流只装 Node 并运行全量门禁，没有 uv。
- 本机环境：uv 0.12.4、Python 3.14.5、Node 25.2.1、Windows PowerShell 5.1。沙箱的网络受限，首次解析依赖需要放行。
- 技术债 CCD-001 的退出条件以"路线图 P0 建立 tests/"为前提，但路线图 P0 的退出条件没有列它。本轮不扩大范围，它留在技术债表里，收尾时提示。
- lime 对照阅读（只读）：lime 仓库根 AGENTS.md 的"协议与质量"，以及 lime 仓库 internal/aiprompts/quality-workflow.md 的"选择最低门禁"。看到的点：每种改动类型绑定一条可执行命令；改了门禁脚本本身，就要验证门禁的行为，不能只查格式。本计划据此给四个任务各做一次触发检查，给 lint 和 lock 各做一次失败探针。

## 写集与避让

### 本轮认领写集

- 新建：`pyproject.toml`、`.python-version`、`uv.lock`（由 uv 生成，不手写）。
- 新建：`src/lime_star/__init__.py`、`src/lime_star/cli/__init__.py`、`src/lime_star/cli/main.py`。
- 新建：`tests/unit/test_cli_args.py`、`tests/integration/test_cli_process.py`，以及 tests 下三个只有一行文档字符串的 `__init__.py`。
- 修改：`scripts/verify-local.mjs`，只动头注释的一句和任务表的 Python 部分。
- 修改（验证中途追加）：`scripts/check-file-size-governance.mjs` 的跳过目录表，加入 Python 工具的三个缓存目录。理由见进度记录。
- 修改：`.github/workflows/quality.yml`，加入 uv 的安装与依赖同步。
- 修改：根 `AGENTS.md` 的高频命令，根 `../../README.md` 的本地门禁说明。
- 修改：`../aiprompts/architecture.md` 中三行的状态列。
- 修改：`README.md` 的当前计划表，以及本计划。

### 只读避让写集

- `../roadmap/agent-practice.md`：路线图规定它是各阶段的只读避让集，阶段结论等仓库所有者验收后再追加。
- `../prd/`：需求已确认，不改。
- scripts 下其余脚本，以及 governance 下的基线与契约清单：不新增脚本，基线不需要更新。
- `package.json`：Python 任务直接调用 uv，不加 npm 脚本。
- `.codex/`：技能入口引用的事实源没有变化。

## 删除集

verify-local.mjs 任务表里两行注释掉的占位任务，由真实的 uv 任务取代。没有其他删除。

## 本阶段的默认选择

1. 不带参数的过渡行为：把用法写到标准错误，退出码 2。落选的备选：打印帮助并以 0 退出，命令什么都没做却报告成功；什么都不输出并以 0 退出，无法区分空命令与卡住。路线图 P1 用 R13.1 取代它。
2. lock 任务排在其余 Python 任务之前。`uv run` 遇到过期的锁文件会自动重写它，lock 排在后面就查不出"提交的锁文件已经过期"。依据是进度记录里的对照探针。
3. `.python-version` 钉 3.14，与验收机上的解释器一致；代码、ruff 和 mypy 仍以 3.11 为目标。落选的备选：钉 3.12，验收机要多下载一个解释器，本地测试用的也不是验收环境的版本。
4. 参数解析手写，不用 argparse。R1.3 要求错误指明未知的参数，决策 D-05 要求界面文案用中文，argparse 的错误文案是英文的。落选的备选：继承 argparse 并覆盖它的 error 方法，为改文案要依赖内部细节，代码并不更短。
5. 版本号只有一个来源，就是包里的 `__version__`，pyproject 用 dynamic 引用它。落选的备选：两处各写一份，再用测试守住同步，多一个会漂移的点。
6. 进程用例里的命令按"与测试解释器装在同一个环境"定位，不靠 PATH。落选的备选：在 PATH 里找 lime-star，可能命中别处安装的同名命令。
7. CI 把 uv 钉在 0.12.4，也就是生成 uv.lock 的版本；setup-uv 钉在精确标签 v10.4.0。落选的备选：都用最新版。setup-uv 没有 v10 这类主版本标签，2026-11-24 用 git ls-remote 核对过；新版 uv 对同一份依赖可能解析出不同的锁，`uv lock --check` 会在 CI 上失败而本地通过。
8. 行数守卫跳过 Python 工具的缓存目录，而不是只删掉出问题的那一个。落选的备选：只删目录，下次沙箱里的 Agent 跑 pytest 还会重现，而仓库所有者未必有权删它。

## 阶段与退出条件

### A 骨架与命令

- 退出条件：`uv sync` 成功并生成 uv.lock；R1.1 到 R1.3 的四个场景在真实进程里逐条通过；`uv run pytest -q` 通过。

### B 门禁与 CI

- 退出条件：verify:local 的任务表包含 lint、typecheck、test:unit、lock，触发路径与路线图 P0 一致；lint 与 lock 的失败探针都被报出；`npm run verify:local -- --full` 通过；CI 工作流装了 uv 并执行 `uv sync`。

### C 验收

- 退出条件：路线图 P0 的四条退出条件都有结果记录。其中"CI 工作流跑通一次"要等仓库所有者提交并推送之后才能核对。

## 验证矩阵

| 阶段 | 命令 | 证据等级 | 结果 |
| --- | --- | --- | --- |
| A | `uv sync`，随后 `uv lock --check` | 依赖声明 | 通过：解析并安装 14 个包，生成 uv.lock（383 行）；`uv lock --check` 退出码 0。执行前工作树里没有 .venv 和 uv.lock；全新克隆留给 CI |
| A | `uv run lime-star --version`，在仓库根与空目录各执行一次；环境里没有 LIME_STAR_ 开头的变量，空目录里没有文件（R1.1-S1、R1.1-S2） | Gate B（路线图 P0 口径：真实启动命令并看到输出；主链尚未建立） | 通过：两次的标准输出都是且只是 17 字节的一行 `lime-star 0.0.0`，退出码 0，标准错误为空 |
| A | `uv run lime-star --help`（R1.2-S1） | Gate B（同上） | 通过：退出码 0，输出含 `--version` 和一句话说明，不含 `--resume` |
| A | `uv run lime-star --nosuch`（R1.3-S1） | Gate B（同上） | 通过：退出码 2，标准输出为空，标准错误点名 `--nosuch`；中文是合法的 UTF-8，已核对字节 |
| A | `uv run pytest -q` | Unit，加 pytest 里的真实进程用例 | 通过：15 条，9 条单元加 6 条真实进程。不替代上面的 Gate B |
| B | `node scripts/verify-local.mjs --dry-run` 加各组路径 | 门禁（任务选择） | 通过：src 与 tests 触发 lint、typecheck、test:unit；pyproject.toml 触发 lock、test:unit；uv.lock 触发 test:unit；`--full` 选中 8 个任务，lock 排在其余 Python 任务之前 |
| B | lint 的失败探针：放一个未使用的导入 | 门禁（负向） | 通过：lint 以 1 退出并报 F401；复原后通过 |
| B | lock 的失败探针：让锁文件过期 | 门禁（负向） | 通过：lock 以 1 退出；`--only test:unit,lock` 时 lock 先失败，test:unit 没有执行。探针前后 pyproject.toml 与 main.py 的 SHA256 一致，uv.lock 没有被改写 |
| B | 行数守卫遇到读不了的 `.pytest_cache` | 门禁（先失败，修复后通过） | 修复前：扫到该目录报 EPERM，门禁以 2 退出。修复后保留该目录重跑：扫描 63 个文件，通过 |
| B | `npm.cmd run verify:local -- --full` | 门禁 | 通过：8 个任务，退出码 0，用时 23.7 秒。本机执行策略是 Restricted，`npm` 会被拦，所以用 npm.cmd |
| B | CI 工作流跑通一次 | CI | 未跑：需要先提交并推送，Agent 不主动执行。风险是工作流从未执行过；触发条件是仓库所有者推送后查看 Actions |
| 全程 | `npm run test:contracts` | 契约检查 | 未跑：本轮没有改协议、契约或 schema，没有风险 |

## 验证合同

非主链改动：P0 只建立命令入口和门禁，不碰回合、模型、工具和持久化。证据等级仍按路线图 P0 的要求，达到 Gate B。

## 架构确认

非重大：三个条目早已在目录地图里登记，本阶段只把状态从"路线图 P0"改为"已有"，没有新增或删除 owner，不改主链、协议和持久化。仓库所有者如果认为新建 src 与 tests 两个顶层目录算重大变更，提出后补确认块。

## 进度记录

每刀一条，按日期追加，不改写历史。

### 2026-11-24

- 改动：新建 uv 项目，解析到 pytest 9.2.0、ruff 0.17.6、mypy 2.4.1。命令入口 `src/lime_star/cli/main.py` 处理 `--version`、`--help`、未知参数和不带参数的过渡行为。tests 下 5 个文件，其中 9 条单元用例加 6 条真实进程用例，覆盖 R1.1-S1、R1.1-S2、R1.2-S1、R1.3-S1 和 R1.3 的边界。verify-local 的任务表接入 lock、lint、typecheck、test:unit。CI 加入 setup-uv 与 `uv sync`。根 AGENTS.md、根 README、architecture.md 的三行状态同步。
- 改动（计划外，验证中途追加）：`scripts/check-file-size-governance.mjs` 的跳过目录表加入 `.pytest_cache`、`.mypy_cache`、`.ruff_cache`。起因：第一次跑全量门禁，行数守卫扫到 `.pytest_cache` 报 EPERM，整个门禁失败。那个目录是 Agent 在沙箱账户下跑 pytest 留下的。pytest 在 Windows 上把缓存目录设成私有，仓库所有者以普通权限读不了它，按验收动作跑门禁会在第一个任务就失败。任何沙箱里的 Agent 再跑一次 pytest 都会重现，所以修守卫，而不只是删目录。沙箱留下的缓存目录随后已全部删除。
- 验证：逐项结果见验证矩阵。补充四点。
  - Gate B 探针的第一次执行把 `uv run` 放在没有项目的空目录里启动，uv 报找不到程序。那是探针的设计错误，不是命令的问题；改用 `--project` 指向仓库后重跑，上面的结果是重跑的。
  - `uv run` 重写锁文件的对照，在临时副本里做：锁文件过期时 `uv lock --check` 以 1 退出；`uv run` 以 0 退出并把 uv.lock 重写；之后 `--check` 通过。这是把 lock 排在最前的依据。
  - 全量门禁之后只改了两处：CI 工作流里 uv 的版本钉定，以及本计划。这两个文件不是任何 Python 任务的输入，所以没有重跑 Python 任务；改完后重跑了三个 Node 守卫和 dry-run，都通过。
  - 三次文件编辑被"恰好命中一次"的断言拦下，都没有写入：一次是 PowerShell 把单对替换展平，两次是我把 architecture.md 的旧文本抄错。按实际文本改正后才写入。
- 观察到但没有处理：
  - test:unit 在全量门禁里用了 10.57 秒，沙箱里单独跑同样的用例是 1.36 秒。原因没有查清；进程用例每条的超时是 30 秒，相距很远。
  - check-doc-links 的全树索引会遍历 .venv 的 2305 个文件，其中 6 个是它能当作候选的文档。整个检查 418 毫秒，影响小，没有挂账。
  - `ruff format --check .` 报"47 files"。verbose 日志显示它实际只格式化了 8 个 Python 文件，这是该版本的计数口径。
- 未验证：
  - CI：没有跑，原因见验证矩阵。
  - Windows 以外的平台：本地只在 Windows 上验证；CI 用 ubuntu-latest，推送后才有一手结果。
  - 3.11 到 3.13 的解释器：没有安装，没有在这些版本上跑过测试。ruff 与 mypy 以 3.11 为目标，只能挡住语法和不兼容的类型用法。
- 完成度：85%。Agent 侧的实现与本地验证已完成，剩余取决于仓库所有者。
- 下一刀：仓库所有者按路线图 P0 的验收动作核对；说"提交"后执行 commit 并推送，确认 CI 通过，然后在路线图的进度记录里追加一条，把本计划标为 done。CCD-001 的退出条件已经具备，建议并入 P1 的计划或单开一刀。
### 2026-11-24（提交）

- 改动：仓库所有者说"提交"。执行 commit，不推送。本计划的状态保持 in_progress，因为路线图 P0 的退出条件还剩"CI 工作流跑通一次"没有核对。
- 验证：提交前核对工作树，与本轮写集一致，没有别的改动；本条写入后重跑三个 Node 守卫，通过。
- 完成度：85%。
- 下一刀：仓库所有者推送后核对 CI。通过后在路线图的进度记录里追加一条，把本计划标为 done，并从 `README.md` 的当前计划表移除。

## 当前结论

- 治理四分类：current 新增 lime-star 命令入口（Surface）、四个 Python 门禁任务、uv 项目骨架和测试。compat、deprecated、dead 均无新增或删除。删掉的只有 verify-local.mjs 里两行注释占位，不属于任何一类。
- 验证结果与未验证原因：见验证矩阵和进度记录。
- 来源声明：对照阅读了 lime 仓库根 AGENTS.md 的"协议与质量"，以及 lime 仓库 internal/aiprompts/quality-workflow.md 的"选择最低门禁"。只取两个做法：改动类型绑定可执行命令；改了门禁脚本就验证它的行为。按本仓库语境使用，没有复制原文。CI 用的版本号与输入项来自 setup-uv 仓库的 release 列表和 action.yml。

完成度: 85%
