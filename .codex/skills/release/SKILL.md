---
name: release
description: 准备并执行 lime-star 的一次发版，覆盖版本号、发布说明、验证门禁以及 commit、tag、推送的确认。当前是骨架，路线图 P7 首次发版时补全并启用。
---

# 发版（骨架）

状态：骨架，尚未启用。启用条件见 `internal/exec-plans/agent-practice-roadmap-plan.md` 的 P7。启用之前不得依据本 skill 执行任何 git 写操作。

## 已确定的原则

- 发版是高风险流程。commit、tag、push 都遵守根 AGENTS.md 的提交规则，经仓库所有者明确确认后才执行。
- 版本号的事实源是 pyproject.toml。改动之后运行 `uv lock --check` 和 `npm run verify:local -- --full`。
- 发版默认目标是完成一次端到端发布：整理改动范围、更新版本与发布说明、跑门禁、commit、tag、push。每一步 git 写操作都要单独确认。
- 发布说明只写用户可观察的变化和已知缺口，不把未验证的部分写成已完成。

## 启用时要补的内容

- 改动范围的盘点清单
- 发布说明的文件位置与格式
- GitHub Release 的产物与标签规则
- 发版验证矩阵
