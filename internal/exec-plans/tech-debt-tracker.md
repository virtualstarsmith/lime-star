# 技术债追踪

登记规则：清理类工作不能直接回挂路线图时进本表；每条必须有退出条件；不允许无退出条件长期滞留。编号递增，不复用；清退后保留行并标记 closed（本表是常驻档案，不随计划删除）。

| 编号 | 主题 | 来源 | 退出条件 | 状态 | 登记日期 |
| --- | --- | --- | --- | --- | --- |
| CCD-001 | 守卫脚本没有仓库内的回归用例；check-doc-links 的修复靠仓库外的临时副本才完成对照验证 | `paradigm-port-plan.md` 的进度记录 | 路线图 P0 建立 tests/ 后，为 check-doc-links 补负向用例并挂进 verify-local 任务表；用例须证明带目录的错误路径会报违规、裸文件名可全树查找 | closed（2026-11-24，见 `p1-chat-plan.md`） | 2026-11-23 |
| CCD-002 | 重大架构变更的确认只有规则，没有守卫 | `../research/lime-paradigm.md` | 首次在 architecture.md 追加 Owner 章节之前，补一个检查确认块的守卫并挂进 verify-local 任务表 | closed（2026-11-24，见 `p2-loop-core-plan.md`） | 2026-11-23 |
| CCD-003 | 依赖方向与禁止旁路只有规则，没有守卫 | `../research/lime-paradigm.md` | agent_runtime 落地之前，补导入边界守卫（至少覆盖 cli 不得绕过 app）并挂进 verify-local 任务表 | closed（2026-11-24，见 `p2-loop-core-plan.md`） | 2026-11-23 |
| CCD-004 | 需求文档的写作要求没有守卫脚本，自检靠 Agent 临时脚本或人工 | `../research/agent-prd-practice.md` | 需求确认后，在 scripts 下的领域目录新增需求自检脚本（编号唯一、每条需求有陈述和场景、未决不超过 5 个、路线图引用的编号存在），写明理由后更新冻结基线，并挂进 verify-local 任务表 | open | 2026-11-23 |
