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

每次模型请求在工作目录的 `.lime-star/logs/requests.jsonl` 里追加一行，只记时间、标识、状态、耗时和 token 用量。输入 `/exit` 退出。

## 本地门禁

需要 Node 18 或更高版本。治理脚本零依赖；Python 任务（lock、lint、typecheck、test:unit、test:guards、architecture）需要 uv，首次运行前先执行一次 `uv sync`。

```bash
uv sync                         # 首次运行前：按 uv.lock 建好 .venv
npm run verify:local            # 按改动路径增量选任务
npm run verify:local -- --full  # 跑全部任务
npm run test:contracts
```

Windows PowerShell 如果提示 `npm.ps1` 无法加载（执行策略禁止运行脚本），把 `npm` 换成 `npm.cmd`，或者直接运行对应的 `node scripts/...` 命令。

## 许可

MIT，见 [LICENSE](LICENSE)。
