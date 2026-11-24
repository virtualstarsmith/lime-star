# lime-star 仓库指南

lime-star 是用 Lime 的开发范式练习开发 Agent 的个人项目。Agent 与开发者在本仓库内的所有行为以下列规则为准；规则与代码冲突时，以代码与稳定测试为最终裁决，并回写规则。

## 事实源

1. 代码仓库是唯一记录系统。影响实现的决策、计划和验证结果必须落在仓库内；聊天记录、口头结论不是事实源。
2. 根文件只保留仓库级约束和导航；领域规则放在 `internal/aiprompts/`，需求放在 `internal/prd/`，路线图放在 `internal/roadmap/`，研究放在 `internal/research/`，执行进度放在 `internal/exec-plans/`。
3. 每种能力只能有一个继续演进的 owner。`current` 可扩展；`compat` 只能委托；`deprecated` 只能迁出；`dead` 应删除并补回流守卫。细则见 `internal/aiprompts/governance.md`。
4. 本项目的业务主链是：`CLI 输入 -> app 回合入口 -> agent_runtime 回合循环 -> model_provider / tool_runtime -> thread_store 的 Thread/Turn/Item transcript -> CLI 投影 / evidence 导出`。新的入口（测试、TUI、远程调用）只能接入 app 回合入口，不得绕过它直接调用循环、模型或工具。
5. 核心代码只能落在 architecture.md 已登记的 owner 目录内；找不到 owner 时先在 `internal/aiprompts/architecture.md` 立 owner，再写代码。
6. 新命名使用短的领域词。禁止把产品品牌、已退役名称或冗长实现词带进新的命令、API、类型、模块和脚本。
7. 已退役实现均为 `dead / deleted / forbidden-to-restore`。能力缺口只能在 current owner 重建；不得恢复依赖、文档入口、fallback 或 compat 包装。
8. 参考实现边界：lime 仓库只用于对照阅读设计与方法，位置见 `internal/aiprompts/architecture.md`。lime 是 GPL-3.0 项目，不得把它的源码或文档原文复制进本仓库；借鉴的设计按本仓库语境重写，并在文件头或执行计划注明参考的 lime 路径。

## 工程约束

1. 全程使用中文；代码注释遵循所在文件既有语言。
2. 先读后写，保持改动集中。
3. 提交规则：Agent 不主动 commit、push、reset 或创建分支。commit 只在仓库所有者对本轮改动验收通过并明确说"提交"之后执行；push 只在仓库所有者明确要求之后执行。
4. 工作树存在未知改动时，遵循 `internal/aiprompts/parallel-agent-collaboration.md`：声明窄写集、避让脏热区，不覆盖他人改动。
5. 重大架构变更必须在同一变更集中更新 `internal/aiprompts/architecture.md`，并由责任开发者在执行计划和 PR 描述填写架构图确认。未确认不得标记完成。
6. 语言分工：产品代码用 Python（uv 管理，3.11 及以上）；Node 只用于零依赖的治理脚本，不写业务逻辑。
7. 非生成文件接近 `800` 行时优先拆分；超过 `1000` 行不得继续堆叠业务逻辑，除非执行计划记录退出条件。守卫：`node scripts/check-file-size-governance.mjs`。
8. 平台以 Windows 为当前验收环境；未在其他平台验证的部分写进未验证原因。
9. `scripts/` 根目录与一级领域目录受冻结基线保护。新增脚本进入 `scripts/<domain>/` 或所属 package；新增一级目录必须在执行计划写明理由后更新基线。守卫：`node scripts/check-scripts-baseline.mjs`。
10. 生产路径不得回退 mock。mock 只允许测试夹具明确使用；夹具、冒烟和业务验证都必须走真实 current 主链。
11. 配置、协议和依赖改动必须同步 schema、消费者、文档、锁文件与测试。守卫：`node scripts/check-contracts.mjs`；Python 依赖锁文件由 `uv lock` 维护。

## 协议与质量

1. 改协议、契约或 schema 时，同步消费者与测试夹具，执行 `npm run test:contracts`，并运行 `node scripts/check-contracts.mjs --update` 登记确认。
2. 普通改动优先运行受影响的定向测试；先窄后宽，不以全量重跑替代定位。
3. 主路径改动至少运行一次真实链路冒烟。证据分级与最低验证矩阵见 `internal/aiprompts/quality-workflow.md`。
4. 真实交互证据分级：Gate A 是读模型或投影级证据；Gate B 必须是真实 CLI 进程、真实输入、贯穿主链的可见输出，模型为真实接口或显式标注的回放夹具。Gate A 不能替代 Gate B。
5. 默认本地门禁为 `npm run verify:local`（编排器见 `scripts/verify-local.mjs`）。
6. 凭证只放 `.env` 或环境变量，不得进入代码、文档、测试夹具、transcript 和证据导出。守卫：`node scripts/security/check-secrets.mjs`，检查 `.env` 未被 Git 跟踪、已跟踪文件里没有常见密钥格式。

## 执行方式

1. 长任务必须更新 `internal/exec-plans/`，记录目标、写集、退出条件、验证和阻塞。模板：`internal/exec-plans/templates/task-plan.md`。
2. 路线图任务先说明主目标、当前阶段和下一刀；治理删除必须直接服务主链交付。
3. 仓库所有者明确无兼容需求时，直接迁移调用并删除旧入口，不新增包装层。
4. 收尾报告必须包含：current、compat、deprecated、dead 四类各自新增或删除了什么；验证结果；未验证项及原因；完成度百分比；来源声明（本轮是否参考了 lime 的内容及其路径）。

## 导航

- 全局架构（唯一裁决源）：`internal/aiprompts/architecture.md`
- 治理：`internal/aiprompts/governance.md`
- 质量工作流：`internal/aiprompts/quality-workflow.md`
- 并行协作：`internal/aiprompts/parallel-agent-collaboration.md`
- 场景化索引：`internal/aiprompts/README.md`
- 需求：`internal/prd/README.md`
- 路线图：`internal/roadmap/README.md`
- 研究：`internal/research/README.md`
- 执行计划：`internal/exec-plans/README.md`
- 治理脚本：`scripts/README.md`
- 范式学习材料：`internal/README.md`
- 项目技能索引：`.codex/skills/README.md`

## 高频命令

```bash
npm run verify:local
npm run test:contracts
node scripts/security/check-secrets.mjs
uv run pytest
uv run ruff check
uv run mypy
```

Python 任务的命令自路线图 P0 起由 verify:local 按改动路径触发；首次运行前先执行 `uv sync`。
