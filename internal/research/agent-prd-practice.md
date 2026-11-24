# 给编码 Agent 写需求：做法对照

> 核对日期：2026-11-23。只读快照，这些仓库此后可能已变化。
> 本页是研究结论，不是规则。规则正文在 `../prd/README.md`，落地记录在 `../exec-plans/prd-alignment-plan.md`。
> 读过的来源（2026-11-23 经 GitHub API 读取原文，星数取当天元数据；未复制原文，按本仓库语境改写）：
> - github/spec-kit：[README](https://github.com/github/spec-kit/blob/main/README.md)、[spec-template.md](https://github.com/github/spec-kit/blob/main/templates/spec-template.md)、[specify.md](https://github.com/github/spec-kit/blob/main/templates/commands/specify.md)、[clarify.md](https://github.com/github/spec-kit/blob/main/templates/commands/clarify.md)、[checklist-template.md](https://github.com/github/spec-kit/blob/main/templates/checklist-template.md)
> - Fission-AI/OpenSpec：[README](https://github.com/Fission-AI/OpenSpec/blob/main/README.md)、[writing-specs.md](https://github.com/Fission-AI/OpenSpec/blob/main/docs/writing-specs.md)
> - bmad-code-org/BMAD-METHOD：[template-agent-spec.md](https://github.com/bmad-code-org/BMAD-METHOD/blob/main/skills/method/bmad-agent-pm/assets/template-agent-spec.md)、[template-prd.md](https://github.com/bmad-code-org/BMAD-METHOD/blob/main/skills/method/bmad-agent-pm/assets/template-prd.md)、[template-prd-light.md](https://github.com/bmad-code-org/BMAD-METHOD/blob/main/skills/method/bmad-agent-pm/assets/template-prd-light.md)、[prepare-long-documents-for-agents.md](https://github.com/bmad-code-org/BMAD-METHOD/blob/main/docs/plan/prepare-long-documents-for-agents.md)
> - gsd-build/get-shit-done：[spec.md](https://github.com/gsd-build/get-shit-done/blob/main/get-shit-done/templates/spec.md)、[requirements.md](https://github.com/gsd-build/get-shit-done/blob/main/get-shit-done/templates/requirements.md)
> - gotalab/cc-sdd：[README](https://github.com/gotalab/cc-sdd/blob/main/README.md)、[需求模板](https://github.com/gotalab/cc-sdd/blob/main/.kiro/settings/templates/specs/requirements.md)、[ears-format.md](https://github.com/gotalab/cc-sdd/blob/main/.kiro/settings/rules/ears-format.md)、[requirements-review-gate.md](https://github.com/gotalab/cc-sdd/blob/main/.kiro/settings/rules/requirements-review-gate.md)
> - eyaltoledano/claude-task-master：[example_prd.md](https://github.com/eyaltoledano/claude-task-master/blob/main/.taskmaster/templates/example_prd.md)
> - BuilderMethods/Agent-OS：[README](https://github.com/BuilderMethods/Agent-OS/blob/main/README.md)、[shape-spec.md](https://github.com/BuilderMethods/Agent-OS/blob/main/commands/agent-os/shape-spec.md)

## 问题

lime-star 的需求文档是给编码 Agent 读的。GitHub 上成熟的规格驱动开发项目怎样写需求、何时澄清、怎样把关、长文档怎样拆，哪些做法适合搬进来。

## 方法

2026-11-23 通过 GitHub API 读取上列文件原文，按"需求怎么写、何时澄清、怎样把关、文件怎么拆"四个问题逐项对照。只读了模板和说明文档。没有做对照实验，"启示"一节是判断。

## 结论

### 1. 规模（事实）

2026-11-23 的 GitHub 星数：github/spec-kit 151111，Fission-AI/OpenSpec 75534，gsd-build/get-shit-done 64115，bmad-code-org/BMAD-METHOD 55652，eyaltoledano/claude-task-master 28528，BuilderMethods/Agent-OS 5634，gotalab/cc-sdd 3775。

### 2. 一条需求怎么写（事实）

- OpenSpec：一条需求只有一个 SHALL 或 MUST，并且可观察；用 RFC 2119 的 MUST、SHOULD、MAY 区分强度。场景是具体的 GIVEN、WHEN、THEN，要能变成自动化测试；要覆盖边界和出错情形，不只走正常路径；标题点明用例。判断标准是没看过代码的测试者能否判定通过。
- spec-kit：功能需求写成"System MUST"加编号；用户故事按优先级排，每条可独立测试，配 Given、When、Then；另有边界情况、关键实体、假设三节；成功标准必须可度量，且不提具体技术。
- cc-sdd：验收标准用 EARS 的五种句式，由 When、While、If、Where 引导的条件句和无条件的"the system shall"；要求可测试、可验证、只描述一个行为。
- BMAD 的 agent-spec：需求同样写成"System MUST"加编号；边界情况只写 Agent 否则会猜错的地方；"Out of scope"写 Agent 不得构建或改动的东西；未决问题在答复前阻塞交付。

### 3. 何时澄清、怎样澄清（事实）

- spec-kit：出规格时对没说的地方做有依据的猜测并写进假设；"NEEDS CLARIFICATION"标记最多 3 处，只用于影响范围或体验、又没有合理默认值的决定。澄清是单独一步，最多 5 个问题，一次问一个，每问带推荐选项；答案写回规格的相应章节，并替换原来的模糊表述，而不是并存；澄清应在做计划之前完成。
- BMAD 的 agent-spec：先出草稿，只问会改变范围、安全或用户体验的问题，每问带推荐答案。
- cc-sdd：写需求前过评审门禁。先做机械检查：每条需求有数字编号、至少一条 EARS 验收标准、没有实现术语；再做判断。最多两轮修改，仍有歧义就停下来问用户，不猜。
- Agent-OS：只在计划模式里做，定位是"塑形"而不是详尽的文档。

### 4. 怎样把关（事实）

- spec-kit：规格写完后按质量清单自检，最多三轮。清单项包括需求可测试且无歧义、成功标准可度量、边界情况已识别、范围有清楚边界、没有实现细节；没过的条目要先改规格才能进入下一步。
- get-shit-done：每条需求必须可证伪，带当前值、目标值和验收方式；验收标准是能判通过或不通过的复选框。

### 5. 文件怎么拆（事实）

- BMAD：文档超过约 50 KB 才处理，有三种结果：不动；按节切成碎片，在主文件放地图；保持单文件，加目录。适合单文件的情形包括需要一口气审阅、各节互相依赖。它提醒：拆成碎片后，漏读一个碎片不会被发现。
- BMAD 按用途分三种模板：完整 PRD 用于多个功能或一个产品；轻量 PRD 用于很简单的项目，约 1250 词；agent-spec 用于交给编码 Agent 的单个功能，含测试与验收，是一份自包含的文件。
- OpenSpec：规格按能力组织，每个能力一个文件，内含需求与场景。
- cc-sdd：每个功能一个目录，需求、设计、任务各一个文件。
- get-shit-done：按文档种类分（项目、需求、路线图），另有每个阶段一份规格。
- Agent-OS：产品上下文、各功能的规格、标准分层存放。

### 6. 其他相关做法（事实）

- get-shit-done 的需求模板：编号形如"类别-序号"；区分首版范围与延后范围；"Out of Scope"表带排除理由；有需求到阶段的追踪表，没有映射到阶段的需求算路线图有缺口。
- claude-task-master 的示例 PRD：按阶段写清每阶段要建什么，明确不排时间，理由是这样才能切成任务。
- BMAD 的完整 PRD 模板：有术语表、决策（选了什么、为什么、击败哪个备选）、未决问题（写明阻塞什么）等节；模型决定用户看到什么时，要有"AI 行为与评估"一节；篇幅上限按层次约 2000 到 3000 词。

### 7. 没核实到的

- OpenAI 官方 Codex 文档：developers.openai.com 返回 403，没有读到。Codex 自动加载哪些项目文档、上限多少，未核实。
- Kiro 官方文档：kiro.dev 的规格页返回 404。EARS 的做法取自 cc-sdd 自带的规则文件，没有和 Kiro 原文对照。
- github/docs 仓库里按文件名没有找到 Copilot 编码 Agent 的规格文档。
- 各项目对格式的硬性校验规则未核实：只读了模板和说明，没有读解析代码。
- BMAD 模板引用的 guidance-planning 和 rubric-planning 没有读。
- 哪种写法让 Agent 实现得更准，没有数据。

## 启示（判断）

- 采纳，已写进 `../prd/README.md` 的写作要求：一条需求一个行为加规范动词；每条需求配"给定、当、则"场景并覆盖出错与边界；范围两头都写；边界情况只写 Agent 会猜错的地方；先出草稿再问，问题不超过 5 个并带推荐答案；写完自检最多三轮。
- 采纳，体现在需求文档的结构上：按能力分文件，每个文件自包含，全局内容放一个文件。依据是 BMAD 的 agent-spec 和 OpenSpec 的按能力组织。比单文件多出的漏读风险，用开工话术给精确路径、每个文件头写明先读什么来抵消。
- 不采纳：需求到阶段的追踪表放 PRD（get-shit-done 的做法），本仓库由路线图承担。每条需求写当前值和目标值（get-shit-done），适合改造已有代码，本仓库从零开始。歧义分数（get-shit-done）是主观打分，不如机械检查。按文档种类把需求、设计、任务放进同一个功能目录（cc-sdd），本仓库已经用分层做到。
- 候选，未排期：需求自检脚本入库，见 `../exec-plans/tech-debt-tracker.md` 的 CCD-004。用对照实验比较单文件与分文件，等路线图 P1 到 P4 有了阶段数据再看有没有必要。
