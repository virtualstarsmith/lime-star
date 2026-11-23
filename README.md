# lime-star

用 Lime 的开发范式练习开发 Agent 的个人项目。目标是一个最小的命令行 Agent：带着项目目录读写文件、执行命令、危险操作经审批、会话可恢复。

代码由 Agent 编写，由仓库所有者验收；规则、计划和验证结果都记录在仓库里。

## 从哪里开始

- Agent 和开发者先读 [AGENTS.md](AGENTS.md)。
- 规则入口与阅读顺序见 [internal/README.md](internal/README.md)。
- 当前进度见 [internal/exec-plans/README.md](internal/exec-plans/README.md)，分阶段路线图见 [internal/roadmap/README.md](internal/roadmap/README.md)。

## 本地门禁

需要 Node 18 或更高版本。门禁脚本零依赖，不需要安装任何包。

```bash
npm run verify:local            # 按改动路径增量选任务
npm run verify:local -- --full  # 跑全部任务
npm run test:contracts
```

Windows PowerShell 如果提示 `npm.ps1` 无法加载（执行策略禁止运行脚本），把 `npm` 换成 `npm.cmd`，或者直接运行对应的 `node scripts/...` 命令。

## 许可

MIT，见 [LICENSE](LICENSE)。
