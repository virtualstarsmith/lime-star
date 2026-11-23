# internal

本目录是 lime-star 的内部事实源，承接规则、需求、路线图、研究、方法论、执行进度和设计目标。对外说明只在根 README.md。

## 子目录

| 目录 | 放什么 | 不放什么 |
| --- | --- | --- |
| `aiprompts/` | 领域规则：架构、治理、质量、并行协作 | 历史日记和实现副本 |
| `develop/` | 范式学习材料与可追踪验收方法论 | 项目进度 |
| `exec-plans/` | 执行计划、阻塞记录、技术债 | 路线图、需求、研究等长期文档 |
| `prd/` | 需求：以用户目标写清做什么、不做什么、怎样算满足 | 实现步骤、排期 |
| `roadmap/` | 路线图：阶段目标、顺序与验收动作 | 逐刀的写集与验证细节 |
| `research/` | 研究：对标调查的结论、来源与核对日期 | 复制来的外部原文 |
| `tech/` | 跨模块设计目标（harness 反馈层） | 实现代码 |
| `test/` | 测试相关的目标形状与任务集（评测） | 测试代码（测试代码在仓库根的 tests/ 下） |

## 阅读顺序

1. 根 AGENTS.md：仓库级硬规则。
2. `internal/aiprompts/README.md`：按场景进入领域文档。
3. `internal/exec-plans/README.md`：当前计划；路线图在 `internal/roadmap/README.md`。
4. 第一次接触这套范式：`internal/develop/paradigm-learning-guide.md`。

## 维护规则

1. 内部长期事实源默认落在本目录。
2. 新增一级子目录时，同步更新本文件、`internal/aiprompts/README.md` 和 `internal/aiprompts/architecture.md` 的目录地图。
3. 能被机器检查的规则优先写成脚本或测试守卫。
4. 被替代且无兼容负担的计划直接删除；历史归 Git。
