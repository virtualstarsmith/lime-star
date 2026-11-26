# lime-star

用 Lime 的开发范式练习开发 Agent 的个人项目。目标是一个最小的命令行 Agent：带着项目目录读写文件、执行命令、危险操作经审批、会话可恢复。

代码由 Agent 编写，由仓库所有者验收；规则、计划和验证结果都记录在仓库里。

## 从哪里开始

- Agent 和开发者先读 [AGENTS.md](AGENTS.md)。
- 规则入口与阅读顺序见 [internal/README.md](internal/README.md)。
- 当前进度见 [internal/exec-plans/README.md](internal/exec-plans/README.md)，分阶段路线图见 [internal/roadmap/README.md](internal/roadmap/README.md)。

## 运行对话命令

路线图 P1 起，不带参数运行 `lime-star` 在工作目录开始一个多轮对话会话：

```bash
uv sync
cp .env.example .env   # 填入 OpenAI 兼容接口的地址、密钥和模型名；也可以改用同名的环境变量
uv run lime-star
```

每次模型请求在工作目录的 `.lime-star/logs/requests.jsonl` 里追加一行，只记时间、标识、状态、耗时和 token 用量。

每个会话有一份会话记录，是工作目录下 `.lime-star/threads/` 里的一个 JSON Lines 文件。用户消息、模型的回复、每次工具调用和它的结果、回合的开始与结局，都按发生顺序写在里面；终端上看到的每一行都来自它。

路线图 P4 起，它可以列出目录、读取工作目录里的 UTF-8 文本文件，也可以写文件和执行命令。文件工具只能访问工作目录里面的路径，越界的会被拒绝。

写文件和执行命令是危险操作：每次执行之前，终端会显示这次要做什么并请求批准，输入 `y` 才执行，别的输入（包括直接回车）都算拒绝。批准和拒绝都会记进会话记录，被拒绝的操作不会执行，模型也不会把它说成已完成。命令不受工作目录的限制，所以批准之前要看清楚命令。命令运行中按 Ctrl+C，会结束它和它的子进程。输入 `/exit` 退出。

## 本地门禁

需要 Node 18 或更高版本。治理脚本零依赖；Python 任务（lock、lint、typecheck、test:unit、smoke:gate-b、test:guards、architecture）需要 uv，首次运行前先执行一次 `uv sync`。

```bash
uv sync                         # 首次运行前：按 uv.lock 建好 .venv
npm run verify:local            # 按改动路径增量选任务
npm run verify:local -- --full  # 跑全部任务
npm run test:contracts
```

Windows PowerShell 如果提示 `npm.ps1` 无法加载（执行策略禁止运行脚本），把 `npm` 换成 `npm.cmd`，或者直接运行对应的 `node scripts/...` 命令。

## 冒烟

Gate B 冒烟在一个真实的 lime-star 进程里跑 MVP 主场景：新建脚本、运行脚本、拒绝一次、运行一条会失败的命令。它对着会话记录和磁盘逐项断言，不看模型自报。

```bash
uv run python scripts/smoke/agent_gate_b.py           # 默认回放录制的夹具，不联网，不需要密钥
uv run python scripts/smoke/agent_gate_b.py --live    # 用 .env 或环境变量里的真实模型，消耗额度
```

退出码 0 表示全部检查通过。本地门禁的 smoke:gate-b 任务跑的是前一种。


## 许可

MIT，见 [LICENSE](LICENSE)。
