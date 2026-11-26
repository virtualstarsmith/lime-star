# Harness 反馈层

> 状态：已接入（2026-11-26）。脚本与入口随路线图 P6 落地，记录见 `../../exec-plans/p6-acceptance-harness-plan.md`。
> 参考来源：lime 仓库 internal/tech/harness/README.md 与 internal/aiprompts/harness-engine-governance.md 的导出链思想，按 lime-star 语境改写。

## 实际入口

```bash
# transcript -> evidence
uv run python scripts/harness/export_evidence.py \
  --transcript .lime-star/threads/<thread_id>.jsonl \
  --out .lime-star/evidence/<thread_id>

# evidence -> replay case（失败样本）
uv run python scripts/harness/promote_replay.py \
  --evidence-dir .lime-star/evidence/<thread_id> \
  --case-dir <样本目录> --case-id <样本标识> --seq <警告指向的序号>

# evidence -> replay case（行为样本：再加 --expect-text，可以重复；--forbid-tool 可选）
uv run python scripts/harness/promote_replay.py \
  --evidence-dir .lime-star/evidence/<thread_id> \
  --case-dir <样本目录> --case-id <样本标识> --seq <这一回合里的任意一项> \
  --expect-text <来源之后的模型文本应包含的说法> --forbid-tool <不得出现的工具>

# replay case -> JSON / Markdown 摘要
uv run python scripts/harness/eval_runner.py
```

评测的任务集与判定规则见 `../../test/harness-evals.md`。

## 目标链

```text
runtime transcript
  -> evidence 导出
  -> replay case
  -> 评测
  -> JSON / Markdown 摘要
```

运行时事实的唯一 owner 是 thread_store 里的 transcript。回放和评测都是派生物，每一层只读上一层：
导出只读会话记录，提升只读证据包，评测只读回放样本和它指向的证据包。

## 固定约束

- **先导出事实，再导出判断。** `events.jsonl` 逐条对应会话记录里的一项，带 `thread_id + seq`、时间和所属回合；`summary.md` 只解释事件文件。没有真实执行过的验证命令时，摘要里没有验证段，不用空列表占位。
- **导出先核对记录。** 同一会话、序号从 1 连续、回合依次闭合才导出；对不上的记录直接报错，不导出另一份解释。
- **有开始、没有结局的回合由读模型判。** 导出把它交给 thread_store 的 `interrupted()`，判定写进摘要的警告；读模型给出的补记项不写回会话记录，那是恢复会话的一方做的事。证据导出不写会话记录。
- **样本固定四件套，样本不带事件。** `input.json`、`expected.json`、`grader.json`、`evidence-links.json`；事实留在证据包里，样本只用相对位置和 `thread_id + seq` 指过去。
- **进仓库的样本不带本机位置。** 提升时把常见的服务器、本机绝对路径换成 `<absolute-path>`；评测时样本或它链接的证据事件里还有这种路径，样本判 invalid。
- **评测照实判。** 每个样本的判定是 pass、fail、invalid 三者之一；`strength` 用需求文档里的词（must、should），应当做到而没做到的记为 gaps 并列出，不挡门禁。
- **展示层不是事实源。** 摘要、文案与证据包冲突时，以 transcript 和证据包为准。

## 守卫

`tests/integration/test_harness.py` 从 app 回合入口产出会话记录，再把三个脚本当真实进程运行：证据逐项与会话记录一致；中断回合的判定不写回记录；样本回到证据包去读，证据包被改或没了结论就变；固定任务集的证据与它存档的会话记录逐项一致。verify-local 的任务 test:harness 和 harness:eval 在这一层变动时运行。
