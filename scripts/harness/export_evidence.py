r"""从一份会话记录导出证据包（需求 R10）。

证据包是 transcript 的只读派生物：events.jsonl 逐条对应记录里的项，summary.md 只解释已经导出的事实。
导出不写会话记录。最后一个回合有开始、没有结局时，交给 thread_store 的读模型去判：
判定写进摘要的警告，读模型给出的补记项不写回记录，那是恢复会话的一方做的事。

    uv run python scripts/harness/export_evidence.py \
        --transcript .lime-star/threads/<thread_id>.jsonl \
        --out .lime-star/evidence/<thread_id>

会话记录不在工作目录的标准位置时用 --workdir 指明工作目录：判中断要知道哪些工具要先经批准，
这取自那个工作目录的工具注册表。
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from lime_star.protocol import Entry
from lime_star.thread_store import BrokenItem, Interrupted, interrupted, read
from lime_star.tool_runtime import default_tools

RUNTIME_DIR = ".lime-star"
THREADS_DIR = "threads"

_BODY_LIMIT = 400
"""摘要里一条结果正文最多显示多少个字符；事件文件里始终是全文。"""

_VERIFICATION = re.compile(
    r"(?:^|[&|;])\s*(?:uv|pytest|python3?|py|node|npm)\b.*(?:test|check|verify|mypy|ruff)",
    re.IGNORECASE,
)
"""保守地认出常见的验证命令；拿不准的普通命令不算验证。"""


class EvidenceError(ValueError):
    """证据导出无法继续：记录自身对不上，或者输出位置不能安全使用。"""


def events(entries: Sequence[Entry]) -> list[dict[str, Any]]:
    """把会话记录逐项投影成证据事件；source（会话标识加序号）是回查记录的唯一键。"""
    _check(entries)
    return [
        {
            "source": {"thread_id": entry.thread_id, "seq": entry.seq},
            "time": entry.time.isoformat(),
            "turn_id": entry.turn_id,
            "type": entry.item.kind,
            **dataclasses.asdict(entry.item),
        }
        for entry in entries
    ]


def warnings(records: Sequence[dict[str, Any]]) -> list[dict[str, str]]:
    """从导出的事实里挑出 R10.3 点名的警告。判断只建立在这些事件上。"""
    found: list[dict[str, str]] = []
    for record in records:
        source = _source(record)
        kind = str(record["type"])
        if kind == "approval" and record["decision"] == "rejected":
            found.append(
                {
                    "source": source,
                    "kind": "rejected_operation",
                    "message": f"{record['name']} 被用户拒绝，没有执行。",
                }
            )
        elif kind == "tool_result":
            found.extend(_result_warnings(records, record, source))
        elif kind == "turn_end" and record["outcome"] in {"cancelled", "interrupted"}:
            found.append(
                {
                    "source": source,
                    "kind": "uncompleted_turn",
                    "message": f"回合没有正常完成：{record['reason']}",
                }
            )
    return found


def _result_warnings(
    records: Sequence[dict[str, Any]], result: dict[str, Any], source: str
) -> list[dict[str, str]]:
    """一条工具结果要警告什么。一次结果只归到最具体的那一类，不重复报。"""
    text = f"{result['summary']}\n{result['content']}"
    if "超出工作目录" in text:
        call = _call_of(records, result)
        name = "工具" if call is None else str(call["name"])
        return [
            {
                "source": source,
                "kind": "out_of_bounds",
                "message": f"{name} 访问了工作目录之外的位置。",
            }
        ]
    if _rejected(records, result):
        return []  # 拒绝已经记在批准项上；它那条出错的结果不是另一次故障
    found: list[dict[str, str]] = []
    if "没有读" in text or "已截断" in text:
        found.append(
            {
                "source": source,
                "kind": "truncated_output",
                "message": "输出被截断，记录里只有已经保留的那一部分。",
            }
        )
    if bool(result["error"]):
        found.append(
            {
                "source": source,
                "kind": "tool_or_command_error",
                "message": "工具或命令返回了出错的结果。",
            }
        )
    return found


def verifications(records: Sequence[dict[str, Any]]) -> list[dict[str, str]]:
    """真实执行过的验证命令；一条都没有时调用方不写验证段。"""
    found: list[dict[str, str]] = []
    for record in records:
        if record["type"] != "tool_result" or bool(record["error"]):
            continue
        call = _call_of(records, record)
        if call is None or call["name"] != "run_command" or not _is_verification(call):
            continue
        found.append(
            {
                "source": _source(record),
                "command": str(call["arguments"]),
                "summary": str(record["summary"] or record["content"]),
            }
        )
    return found


def summary(records: Sequence[dict[str, Any]], cut: Interrupted | None = None) -> str:
    """可读摘要：先列时间线和工具结果，再列警告；有验证命令时才列验证记录。"""
    records = list(records)
    thread_ids = sorted({str(record["source"]["thread_id"]) for record in records})
    lines = [
        f"# 证据摘要：{'，'.join(thread_ids)}",
        "",
        "本摘要只解释 events.jsonl 里的导出事实。",
        "",
        "## 时间线",
        "",
    ]
    lines.extend(
        f"- `{_source(record)}` `{record['type']}` {_one_line(record)}" for record in records
    )
    lines.extend(["", "## 工具与命令结果", ""])
    results = [record for record in records if record["type"] == "tool_result"]
    if not results:
        lines.append("- 无")
    for record in results:
        call = _call_of(records, record)
        name = "未知工具" if call is None else str(call["name"])
        state = "出错" if bool(record["error"]) else "完成"
        lines.append(f"- `{_source(record)}` {name}（{state}）：{_body(record)}")
    lines.extend(["", "## 警告", ""])
    found = warnings(records)
    if cut is not None:
        found.append(
            {
                "source": _last_of_turn(records, cut.turn_id),
                "kind": "uncompleted_turn",
                "message": f"{cut.reason}（读模型的判定；补记项没有写进会话记录）",
            }
        )
    if not found:
        lines.append("- 无")
    lines.extend(f"- `{item['source']}` {item['kind']}：{item['message']}" for item in found)
    verified = verifications(records)
    if verified:
        lines.extend(["", "## 验证记录", ""])
        lines.extend(
            f"- `{item['source']}` `{item['command']}`：{item['summary']}" for item in verified
        )
    lines.append("")
    return "\n".join(lines)


def export(transcript: Path, out: Path, workdir: Path | None = None) -> list[dict[str, Any]]:
    """读一份会话记录并写出证据包；返回写出的证据事件。会话记录只读。"""
    if not transcript.is_file():
        raise EvidenceError(f"读不到会话记录：{transcript}")
    try:
        entries = read(transcript)
        records = events(entries)
        cut = interruption(entries, workdir if workdir is not None else _workdir_of(transcript))
    except BrokenItem as exc:
        raise EvidenceError(f"会话记录读不懂（{exc}）。") from exc
    if out.exists() and any(out.iterdir()):
        raise EvidenceError(f"证据目录已存在且有内容：{out}")
    out.mkdir(parents=True, exist_ok=False)
    _write_jsonl(out / "events.jsonl", records)
    (out / "summary.md").write_text(summary(records, cut), encoding="utf-8", newline="\n")
    return records


def interruption(entries: Sequence[Entry], workdir: Path) -> Interrupted | None:
    """最后一个回合有开始、没有结局时，用 thread_store 的读模型判它；这里不另写一份判定。"""
    try:
        return interrupted(entries, default_tools(workdir).dangerous())
    except BrokenItem as exc:
        raise EvidenceError(f"会话记录的回合结构不对（{exc}）。") from exc


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--transcript", type=Path, required=True, help="会话记录的 JSONL 文件")
    parser.add_argument("--out", type=Path, required=True, help="证据包输出目录，必须还不存在")
    parser.add_argument("--workdir", type=Path, help="会话记录所属的工作目录；默认从记录的位置推出")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        records = export(args.transcript, args.out, args.workdir)
    except (OSError, ValueError) as exc:
        print(f"证据导出失败：{exc}", file=sys.stderr)
        return 2
    print(f"已导出 {len(records)} 条证据事件到 {args.out}")
    return 0


def _check(entries: Sequence[Entry]) -> None:
    """同一份记录必须是同一会话，序号从 1 连续；回合依次闭合，只有最后一个回合可以没有结局。"""
    if not entries:
        raise EvidenceError("会话记录是空的，没有可导出的证据。")
    thread_id = entries[0].thread_id
    if any(entry.thread_id != thread_id for entry in entries):
        raise EvidenceError("会话记录里有不属于同一会话的项。")
    if [entry.seq for entry in entries] != list(range(1, len(entries) + 1)):
        raise EvidenceError("会话记录的序号不连续。")
    open_since = False
    for entry in entries:
        kind = entry.item.kind
        if kind == "turn_start":
            if open_since:
                raise EvidenceError("有一个回合没有结局，后面却又开始了一个回合。")
            open_since = True
        elif kind == "turn_end":
            if not open_since:
                raise EvidenceError("有回合结局，前面却没有回合开始。")
            open_since = False
        elif not open_since:
            raise EvidenceError("有回合开始之前就写下了别的项。")


def _workdir_of(transcript: Path) -> Path:
    """会话记录在工作目录的 .lime-star/threads 下时，从它的位置推出工作目录。"""
    if transcript.parent.name == THREADS_DIR and transcript.parent.parent.name == RUNTIME_DIR:
        return transcript.parent.parent.parent
    raise EvidenceError("无法从会话记录的位置推出工作目录，请用 --workdir 指明。")


def _source(record: dict[str, Any]) -> str:
    return f"{record['source']['thread_id']}#{record['source']['seq']}"


def _last_of_turn(records: Sequence[dict[str, Any]], turn_id: str) -> str:
    return _source([record for record in records if record["turn_id"] == turn_id][-1])


def _one_line(record: dict[str, Any]) -> str:
    """把一条事件压成一行；JSON 编码保证换行和控制字符不破坏摘要。"""
    kind = str(record["type"])
    if kind == "tool_call":
        text = f"{record['name']} {record['arguments']}"
    elif kind == "approval":
        text = f"{record['name']}：{record['decision']}"
    elif kind == "tool_result":
        text = str(record["summary"] or record["content"])
    elif kind == "turn_end":
        text = f"{record['outcome']} {record['reason']}".strip()
    else:
        text = str(record.get("content", ""))
    return json.dumps(text, ensure_ascii=False)


def _body(record: dict[str, Any]) -> str:
    """交给模型的结果正文；太长时只留开头，并指明全文在事件文件的哪一条。"""
    content = str(record["content"])
    if len(content) <= _BODY_LIMIT:
        return json.dumps(content, ensure_ascii=False)
    head = json.dumps(content[:_BODY_LIMIT], ensure_ascii=False)
    return f'{head[:-1]}…（共 {len(content)} 个字符，全文在 events.jsonl 的这一条）"'


def _call_of(records: Sequence[dict[str, Any]], result: dict[str, Any]) -> dict[str, Any] | None:
    """一条结果对应的调用：同一回合里、结果之前、编号相同的最后一次工具调用。"""
    return _before(records, result, "tool_call")


def _rejected(records: Sequence[dict[str, Any]], result: dict[str, Any]) -> bool:
    approval = _before(records, result, "approval")
    return approval is not None and approval["decision"] == "rejected"


def _before(
    records: Sequence[dict[str, Any]], record: dict[str, Any], kind: str
) -> dict[str, Any] | None:
    seq, turn_id = int(record["source"]["seq"]), str(record["turn_id"])
    for index in range(len(records) - 1, -1, -1):
        earlier = records[index]
        if (
            earlier["type"] == kind
            and earlier["turn_id"] == turn_id
            and earlier.get("call_id") == record["call_id"]
            and int(earlier["source"]["seq"]) < seq
        ):
            return earlier
    return None


def _is_verification(call: dict[str, Any]) -> bool:
    try:
        arguments: Any = json.loads(str(call["arguments"]))
    except ValueError:
        return False
    command = str(arguments.get("command", "")) if isinstance(arguments, dict) else ""
    return bool(_VERIFICATION.search(command))


def _write_jsonl(path: Path, records: Sequence[dict[str, Any]]) -> None:
    """逐事件写出 JSON Lines：UTF-8、LF、每行一项。"""
    text = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
    path.write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    raise SystemExit(main())
