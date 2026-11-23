# 范式搬运计划

状态: done
日期: 2026-11-23
主目标: 把 Lime 的开发范式六层搬入 lime-star，使新 Agent 只读仓库文件就能知道规则在哪、改哪个目录、跑什么命令、什么算完成。

## 目标

lime-star 是用 Lime 的开发范式练习开发 Agent 的项目。本计划先为规则、事实源、计划、验证、验收、反馈六层建立仓库内的落点，产品路线由 ../roadmap/agent-practice.md 承接。成功后，任何新开的 Agent 会话不需要聊天背景即可按仓库规则工作。

## 当前事实

- 起始状态：lime-star 只有 README.md（一行标题）和 MIT LICENSE，main 分支一个提交，远端在 GitHub。
- 范式来源一：本机已有的 dev-paradigm-kit 模板，内容是从 lime 提炼的规则、执行计划模板和零依赖治理脚本。
- 范式来源二：lime 仓库，只对照阅读，不改其文件。
- kit 覆盖规则、事实源、计划、验证四层和并行协作；不覆盖项目技能、验收方法论、harness 反馈层和 CI。
- 许可：lime 为 GPL-3.0，lime-star 为 MIT。kit 文件原样取用；kit 没有的部分一律按 lime-star 语境改写，不复制 lime 原文。
- 环境：本机有 Node（npm 11.6.2）、uv 与 Python 3.11.15。

## 写集与避让

### 本轮认领写集

- 根目录：AGENTS.md、README.md、package.json、.gitignore
- .codex/skills/：README 与 governance、quality-workflow、acceptance-loop、skill-factory、release 五个 skill
- .github/workflows/quality.yml
- governance/：四个基线文件
- scripts/：五个脚本与 README
- internal/：README、aiprompts/、develop/、exec-plans/、prd/、roadmap/、research/、tech/harness/、test/

### 只读避让写集

- LICENSE：不改。
- lime 仓库与 dev-paradigm-kit：只读来源。

## 删除集

无。README.md 原有的一行标题被改写为项目说明，属于直接替换。

## 阶段与退出条件

### P0 范式落盘

- 退出条件：kit 模板文件全部到位，适配标记清零，六层在仓库里各有落点。

### P1 接入仪式

- 退出条件：scripts 与行数基线生成；`npm run verify:local -- --full` 通过。

### P2 路线图

- 退出条件：路线图 P0 到 P7 每阶段七项齐全；引用的 lime 路径逐条存在。

### P3 冷启动验收（由仓库所有者执行）

- 退出条件：在 lime-star 新开 Agent 会话，只问四个问题，答案与仓库文件一致。

## 验证矩阵

| 阶段 | 命令 | 证据等级 | 结果 |
| --- | --- | --- | --- |
| P0 | rg 统计适配标记数量 | 门禁 | 通过：AGENTS.md、internal、scripts、.codex 下 0 处 |
| P0 | node scripts/check-doc-links.mjs | 门禁 | 通过：扫描 20 个文档、74 个路径引用 |
| P0 | check-doc-links 新旧对照（临时副本加 --root，见进度记录） | 门禁 | 通过：干净副本新旧均退出码 0；3 个带错状态旧脚本报 0、0、2 处，新脚本报 1、3、4 处并退出码 1 |
| P0 | 三层登记后的文档链接与引用检查：node scripts/check-doc-links.mjs；全仓搜索旧路线图文件名 | 门禁 | 通过：25 个文档、93 个路径引用全部按路径解析；旧文件名只剩进度记录里的历史说明 |
| P0 | 验收修订后的文档链接与引用检查 | 门禁 | 通过：25 个文档、101 个路径引用全部按路径解析；旧需求文件名只剩进度记录里的历史说明；被要求删除的观察无残留 |
| P1 | node scripts/check-scripts-baseline.mjs --update | 门禁 | 通过：根文件 6 个、一级目录 0 个 |
| P1 | node scripts/check-file-size-governance.mjs --update | 门禁 | 通过：扫描 39 个文件、0 个超线 |
| P1 | node scripts/verify-local.mjs --full | 门禁 | 通过：4 个任务，退出码 0 |
| P1 | npm run verify:local -- --full | 门禁 | 通过：与 node 形式等价，退出码 0 |
| P1 | CI quality.yml | CI | 通过：push 23171af 后的 run 45172278363，verify 作业成功，步骤 Local gate (full) 成功；环境 ubuntu-latest 加 Node 22 |
| P2 | lime 路径存在性核对 | 静态核对 | 通过：路线图引用的 lime 路径逐条存在 |
| P3 | 冷启动测试 | 人工验收 | 第一轮已跑（2026-11-23）：四问均可从仓库文件答出，另发现文档与仓库不一致并已修复，见进度记录。第二轮（同日，新起子会话，只给四问）：路径、命令与事实全部与文件一致，两处表述偏差见进度记录。仓库所有者于 2026-11-23 确认通过 |
| 收尾 | 全部退出条件复验：路线图七项、lime 路径存在性、目录地图与实际目录双向核对、AGENTS.md 路径、适配标记搜索、npm.cmd run verify:local -- --full | 门禁与静态核对 | 通过：8 个阶段七项齐全；11 条 lime 路径存在；12 个目录双向一致；适配标记 0 处；门禁 4 个任务通过，退出码 0 |

## 验证合同

非产品主链改动：本计划只建立工程制度与文档，不写产品代码，不填 Agent 验证合同。

## 架构确认

Architecture impact: major

架构图已更新：internal/aiprompts/architecture.md（新建，含目录地图、业务主链、依赖方向）

Responsible developer confirmation: 仓库所有者，2026-11-23

确认内容：本次新增治理目录与规则文件，确定目标布局与唯一业务主链；产品代码目录尚未创建。回滚方式是还原本计划写集涉及的文件。2026-11-23 同一变更集内追加：按仓库所有者要求新增 internal/prd、internal/roadmap、internal/research 三个事实源层，路线图文件从 exec-plans 移入 roadmap，"需求"加入裁决顺序第 5 级；这三项的回滚是把路线图文件移回 exec-plans 并删除三个目录。同日按仓库所有者意见，根 AGENTS.md 的事实源分层与导航、根 README.md 的入口说明一并更新，属于同一确认范围。

## 进度记录

### 2026-11-23

- 改动：新增根 AGENTS.md、package.json、.gitignore 与 CI 工作流，改写 README.md；internal 下新增 aiprompts（5 份）、develop（3 份）、exec-plans（README、2 个模板、技术债表、本计划、路线图）、tech/harness 与 test 的目标骨架；scripts 下 5 个脚本与 README；governance 下 4 个基线；.codex/skills 下索引与 5 个 skill。
- 验证（首次全量门禁）：接入仪式三个命令退出码均为 0；dry-run 显示改动文件 38 个、选中 4 个任务；verify-local --full 的 4 个任务全部通过。证据等级：门禁（静态检查与基线生成），不涉及 Gate A 或 Gate B。
- 收尾复跑：写入本记录后再次运行 node scripts/verify-local.mjs --full，4 个任务通过，退出码 0；适配标记计数仍为 0。
- 未跑：CI（需要 push）；冷启动测试（需要仓库所有者在新会话里执行）。
- 完成度：90%
- 下一刀：仓库所有者执行验收并做冷启动测试；通过后说"提交"；首次 push 后确认 CI；然后进入路线图 P0。

### 2026-11-23（冷启动验收第一轮与修复）

- 改动：新会话只凭仓库文件回答"规则在哪、改哪个目录、跑什么命令、什么算完成"，四问均可答出；另发现文档与仓库不一致，修复了三个文件。internal/aiprompts/README.md：场景路由里 scripts/README.md 的相对路径由 ../scripts 改为 ../../scripts。internal/aiprompts/architecture.md：目录地图补登 .github/。internal/develop/paradigm-quick-checklist.md：共享热区一项改为指向 parallel-agent-collaboration.md 第 3 节的清单，"legacy 守卫"改为 governance.md 的用语"负向守卫"，并删除 package.json 里不存在的 npm run verify:app-version 一行。
- 验证：npm.cmd run verify:local -- --full 的 4 个任务通过，退出码 0；doc-links 检查 75 个路径引用。本机 Windows PowerShell 的执行策略拦截 npm.ps1，所以用 npm.cmd 形式。证据等级：门禁（静态检查）。
- 收尾复跑：写入本记录后再次运行同一条命令，结果相同。
- 未跑：CI（需要 push，仓库所有者尚未要求）；新会话复测（是否需要由仓库所有者决定）。
- 完成度：90%
- 下一刀：仓库所有者判定 P3；通过后说"提交"；首次 push 后确认 CI；然后进入路线图 P0。

### 2026-11-23（守卫修复与 Windows 说明）

- 改动：修复 check-doc-links.mjs 的两处漏洞。其一，解析候选里的"仓库根/template"会把 ../X 归一化成根相对路径 X，冷启动发现的 ../scripts/README.md 就是被它放行的；其二，按路径找不到时退回按文件名全树匹配，带目录的错误路径只要有同名文件就通过。修法：删除 template 候选；引用只能解析到仓库根以内；带目录的引用必须按路径找到，只有裸文件名可按文件名全树查找；违规时提示同名文件的位置。scripts/README.md 同步了规则说明。新规则拦下 3 个现存引用并已改正：paradigm-learning-guide.md 第 125 行的两个 templates/ 路径补全为 internal/exec-plans/templates/；internal/test/harness-evals.md 第 25 行的 ../../exec-plans 改为 ../exec-plans，这是真断链。根 README.md 的门禁一节补充 Windows PowerShell 拦截 npm.ps1 时改用 npm.cmd 或 node scripts/... 的说明。
- 验证：新旧脚本在同一批临时副本上对照（--root 指向仓库副本）。干净副本新旧均通过，75 个路径引用；放回 ../scripts/README.md、放回 3 个错误路径、加入 6 条探针这三个带错状态，旧脚本分别报 0、0、2 处，新脚本分别报 1、3、4 处且退出码 1；探针中裸文件名与根相对路径两条正常引用，新脚本不报。node --check 通过。npm.cmd run verify:local -- --full 的 4 个任务通过，退出码 0。证据等级：门禁（静态检查）。
- 收尾复跑：写入本记录后再次运行同一条命令，结果相同。
- 局限：对照用的副本与快照在仓库外的临时目录，干净克隆上不能复现；守卫脚本目前没有仓库内的回归用例。
- 未跑：CI（需要 push，仓库所有者尚未要求）。
- 完成度：90%
- 下一刀：仓库所有者判定 P3；通过后说"提交"；首次 push 后确认 CI；然后进入路线图 P0。

### 2026-11-23（新增需求、路线图、研究三层）

- 改动：仓库所有者决定建立 prd、roadmap、research 三层。新增 internal/prd、internal/roadmap、internal/research，各带一份 README 和一份种子文档：prd/agent-mvp.md 是由现有目标归纳的需求草稿，待仓库所有者确认；research/lime-paradigm.md 是对照 lime 的研究结论。路线图文件由 internal/exec-plans/agent-practice-roadmap-plan.md 移为 internal/roadmap/agent-practice.md，内容只改了第 13 行一处相对路径。architecture.md 的目录地图登记三个 owner，exec-plans 一行去掉"路线图"，裁决顺序第 5 级加入"需求"。internal/README.md、internal/aiprompts/README.md 的场景路由、internal/exec-plans/README.md、parallel-agent-collaboration.md 的共享热区清单、internal/test/harness-evals.md 同步了路径。根 AGENTS.md 的导航没动，它的"执行计划与路线图"仍指向 internal/exec-plans/README.md，由那里转到路线图。
- 验证：node scripts/check-doc-links.mjs 通过，25 个文档、93 个路径引用全部按路径解析；全仓搜索旧文件名只剩本记录里的历史说明；npm.cmd run verify:local -- --full 的 4 个任务通过，退出码 0。证据等级：门禁（静态检查）。
- 收尾复跑：写入本记录后再次运行同一条命令，结果相同。
- 未跑：CI（需要 push，仓库所有者尚未要求）。
- 完成度：90%
- 下一刀：仓库所有者确认需求草稿和架构确认块；判定 P3；通过后说"提交"；首次 push 后确认 CI；然后进入路线图 P0。

### 2026-11-23（三层的验收修订）

- 改动：仓库所有者对上一刀提了五条意见，逐条处理。其一，认可路线图文件的搬动和改名。其二，需求文档改名为 prd/agent-practice.md，与路线图同名配对，内容从只覆盖 MVP 扩到覆盖路线图已承诺的 P0 到 P6：新增功能需求表 R1 到 R11，每条标注交付它的阶段，全部归纳自各阶段的退出条件，没有新增范围；路线图文件开头加了指向需求的一行，roadmap/README.md 与 prd/README.md 写明路线图与需求互相指向。其三和其四，根 AGENTS.md 整体同步：事实源第 2 条补上需求、路线图、研究三个目录，导航加三行并把"执行计划与路线图"改为"执行计划"；根 README.md 的入口说明改为分别指向执行计划和路线图；这些计入同一个架构确认块。其五，research/lime-paradigm.md 删去 lime 未守住自身规则的观察和 Git 历史未查的说明，相关小节重新编号。
- 验证：node scripts/check-doc-links.mjs 通过，25 个文档、101 个路径引用全部按路径解析；全仓搜索旧需求文件名只剩本计划进度记录里的历史说明，被要求删除的内容无残留；npm.cmd run verify:local -- --full 的 4 个任务通过，退出码 0。证据等级：门禁（静态检查）。
- 收尾复跑：写入本记录后再次运行同一条命令，结果相同。
- 未跑：CI（需要 push，仓库所有者尚未要求）。
- 完成度：90%
- 下一刀：仓库所有者确认需求草稿 agent-practice.md 与架构确认块；判定 P3；通过后说"提交"；首次 push 后确认 CI；然后进入路线图 P0。

### 2026-11-23（收尾复验）

- 改动：本刀不改规则和结构，只做收尾。对计划的全部退出条件重新取证，见验证矩阵的"收尾"一行。把这几轮发现、路线图没有安排的三项欠账登记进技术债表，替换了原有的示例行：CCD-001 守卫脚本没有仓库内回归用例，CCD-002 架构确认没有守卫，CCD-003 依赖方向没有守卫，各带退出条件。"当前结论"按最终的文件清单重写。
- 验证：路线图 P0 到 P7 每阶段七项齐全；对照阅读引用的 11 条 lime 路径逐条存在；12 个实际目录全部登记在目录地图，地图里标"已有"的目录全部存在；AGENTS.md 的路径全部存在；按常见形态搜索适配标记为 0 处，kit 的原始标记串没有记录在计划里，这是一次代理核对；npm.cmd run verify:local -- --full 的 4 个任务通过，退出码 0。证据等级：门禁与静态核对。
- 收尾复跑：写入本记录后再次运行同一条命令，结果相同。
- 未跑：CI（需要 push，仓库所有者尚未要求）；新会话冷启动复测（第一轮已在本会话执行，布局变更后是否复测由仓库所有者决定）。
- 完成度：95%。冷启动测试已执行，所以从 90% 前进；CI 未跑，不计入完成。
- 下一刀：只剩仓库所有者能做的三件事：判定 P3，并确认架构确认块与需求草稿；说"提交"；要求 push。首次 push 后由 Agent 回写 CI 结果，把完成度写到 100%，然后进入路线图 P0。

### 2026-11-23（P3 第二轮：新会话冷启动）

- 改动：仓库所有者要求启动 P3。起了一个不继承本对话上下文的子会话，提示只有四个问题加一句只读约束，它自行读仓库作答。本刀不改任何规则或结构，只记录结果。
- 核对：逐条对照它回答里的路径、命令和事实。规则在哪：十类事实源和裁决顺序全部正确，包括新增的需求、路线图、研究三层。改哪个目录：目录地图、依赖方向、冻结基线、共享热区清单全部正确。跑什么命令：门禁、文档守卫、契约检查、P0 起的 Python 命令、P4 起的冒烟命令全部正确，并正确说明 Python 命令尚未接入。什么算完成：阶段退出条件、证据等级、收尾报告五项、提交规则全部正确。基准时间之后没有任何文件被修改。
- 两处表述偏差：其一，它说每轮动手前都要建 p<N>-<主题>-plan.md 并声明三段写集；文件里是长任务才建计划，专项计划叫 <topic>-plan.md，p<N> 是路线图阶段计划的命名，三段写集是并行场景的要求。其二，它列的打回条件第二条是验证记录可复现，路线图里是低级证据冒充高级证据。两处都是子会话的概括偏差，对应的原文没有歧义，没有需要修改的文件。
- 局限：子会话与本会话用同一个模型、同一套环境注入，不等于仓库所有者亲手开的新会话。
- 结论：Agent 核对认为四问的主干答案与仓库文件一致；P3 的退出条件是否满足，由仓库所有者判定。
- 未跑：CI（需要 push，仓库所有者尚未要求）。
- 完成度：95%
- 下一刀：仓库所有者判定 P3，确认架构确认块与需求草稿；说"提交"；要求 push。首次 push 后由 Agent 回写 CI 结果，把完成度写到 100%，然后进入路线图 P0。

### 2026-11-23（提交、push 与 CI）

- 改动：仓库所有者说"提交"后提交本变更集：23171af（main），43 个文件，新增 2983 行、删除 1 行，提交说明为"落地 Lime 开发范式并建立 Agent 实践路线图"。仓库所有者同意 push 后推送到 origin/main，远端 main 指向 23171af。push 前预检：86 个带目录的路径引用，大小写与真实文件一致，因为 CI 在 Linux 上区分大小写；仓库内 44 个文件均为 LF，本机 core.autocrlf 为 true，没有加 .gitattributes。
- 验证：CI 工作流 quality 在 GitHub 上运行成功，run 45172278363，对应提交 23171af；verify 作业的 Local gate (full) 步骤成功，即 node scripts/verify-local.mjs --full 在 ubuntu-latest 加 Node 22 上通过。这是门禁第一次在 Linux 与 Node 22 上通过。证据等级：CI，来源是 GitHub Actions 的运行记录与作业明细。
- 未确认：架构确认块、需求草稿 agent-practice.md 与 P3 仍待仓库所有者确认。按规则，未确认的重大架构变更不标记 done，所以状态保持 in_progress。
- 完成度：100%。Agent 侧的工作与全部机器验证（本地门禁、CI）均已完成；标记 done 还差上面三项确认。
- 下一刀：仓库所有者确认架构确认块、需求草稿与 P3；说"提交"后提交本记录，并在被要求时 push；然后进入路线图 P0。

### 2026-11-23（确认与收尾）

- 改动：仓库所有者回复"确认，提交并 push"，确认了三项：架构确认块、需求草稿 agent-practice.md、P3 冷启动验收。架构确认块填入确认人与日期；需求文档状态改为已确认，prd/README.md 的清单和路线图文件里的"需求"一行同步；P3 的矩阵行记为确认通过。计划状态改为 done，并从 exec-plans/README.md 的当前计划表移除。计划文件保留，因为技术债表、研究文档和路线图都引用它的进度记录。
- 验证：npm.cmd run verify:local -- --full 的 4 个任务通过，退出码 0。证据等级：门禁。
- 完成度：100%
- 下一刀：进入路线图 P0，开工话术见路线图。

## 当前结论

- 治理四分类：current 为下列全部文件：根目录的 AGENTS.md、README.md、package.json、.gitignore 和 CI 工作流；internal/aiprompts 下 4 份规则加索引；internal/develop 下 3 份方法论与学习材料；internal/exec-plans 下 README、2 个模板、技术债表和本计划；internal/prd、internal/roadmap、internal/research 各一份 README 加一份文档；internal/tech/harness 与 internal/test 的目标骨架；scripts 下 5 个脚本加 README；governance 下 4 个基线；.codex/skills 下索引与 5 个 skill。compat、deprecated、dead 均无新增或删除。
- 验证结果与未验证原因：见验证矩阵，本地门禁与 CI 均已通过，没有未验证项。架构确认块、需求草稿与 P3 已由仓库所有者于 2026-11-23 确认。
- 来源声明：kit 模板文件原样取用，其中 verify-local.mjs 只改了任务表，check-doc-links.mjs 另改了解析规则（见进度记录），其余脚本和两份学习材料只替换了适配标记与路径前缀（paradigm-quick-checklist.md 另在冷启动修复中改了三行，见进度记录）。kit 没有的部分按 lime-star 语境改写，参考的 lime 路径如下，未复制其原文：AGENTS.md 的提交规则与收尾格式；internal/aiprompts 下的 architecture、governance、quality-workflow、parallel-agent-collaboration；internal/develop/traceable-agent-acceptance-methodology.md；internal/tech/harness/README.md；internal/aiprompts/harness-engine-governance.md；internal/test/harness-evals.md；.codex/skills 下的 lime-governance、lime-quality-workflow、lime-product-e2e-loop、project-skill-factory、lime-release-workflow。internal/research/lime-paradigm.md 另引用了 lime 的以下路径，同样只读未复制：AGENTS.md；internal/README.md；internal/aiprompts 下的 architecture.md、governance.md、quality-workflow.md、README.md、parallel-agent-collaboration.md、project-heatmap.md、harness-engine-governance.md；internal/exec-plans/README.md 与 tech-debt-tracker.md；internal 各一级目录的文件清单；package.json 的 scripts；scripts 的文件清单；.github/workflows 下的 quality.yml 与 harness-nightly.yml；.husky/pre-commit；.codex/skills/README.md。

完成度: 100%
