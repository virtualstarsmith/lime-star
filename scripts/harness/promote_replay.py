r"""把证据包里的一次失败或一段行为提升成仓库内的回放样本（需求 R11.2、R11.3）。

样本由四个文件组成：input、expected、grader、evidence-links。提升脚本只读证据包，不回读会话记录，
也不把事件复制进样本：评测时经 evidence-links 回到证据包去读。
写出的字符串先把本机绝对路径换成占位路径。

失败样本：--seq 指向一条被拒绝的操作、一条出错的结果或一个没有结局的回合。
行为样本：再加 --expect-text（可以重复），--seq 指向这一回合里的任意一项，判定的是它之后的模型文本；
        --forbid-tool（可以重复）列出这一回合里不得出现的工具调用。

    uv run python scripts/harness/promote_replay.py \
        --evidence-dir .lime-star/evidence/<thread_id> \
        --case-dir tests/fixtures/harness/<case-id> \
        --case-id <case-id> --seq <序号>
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

EVENTS = "events.jsonl"
PLACEHOLDER = "<absolute-path>"
_STOP = r"\s\\/:*?\"<>|,;()\[\]{}，。；：！？、（）【】“”‘’"
"""路径里不会出现、或者到了就该停下的字符。"""

_SPACED = re.compile(
    r"(?:[A-Za-z]:[\\/]+)?(?:Program Files(?: \(x86\))?|Application Data)[\\/][^\s\"']*"
)
_UNC = re.compile(
    r"(?<![\\\w:])\\{2,4}[A-Za-z0-9._-]+(?:\\+[^\s\\/:*?\"<>|,;()，。；：！？、（）【】“”’]+)+"
)
_WINDOWS = re.compile(rf"(?<![A-Za-z])[A-Za-z]:[\\/]+(?:[^{_STOP}]+[\\/]+)*[^{_STOP}]+")
_POSIX = re.compile(rf"(?<![\w:])/(?:home|Users|tmp|var|mnt|opt|private)(?:/[^{_STOP}]+)+")
FILES = ("input.json", "expected.json", "grader.json", "evidence-links.json")


class ReplayError(ValueError):
    """样本提升不了：证据包不完整、要提升的那一项不对，或者输出位置写不下。"""


def load_events(evidence_dir: Path) -> list[dict[str, Any]]:
    """读证据包的逐事件文件。这是提升脚本唯一的事实输入。"""
    path = evidence_dir / EVENTS
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ReplayError(f"读不到证据事件 {path}（{exc}）") from exc
    records: list[dict[str, Any]] = []
    for number, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value: Any = json.loads(line)
        except ValueError as exc:
            raise ReplayError(f"{EVENTS} 第 {number} 行不是 JSON") from exc
        if not isinstance(value, dict) or not isinstance(value.get("source"), dict):
            raise ReplayError(f"{EVENTS} 第 {number} 行不是带 source 的证据事件")
        records.append(value)
    if not records:
        raise ReplayError("证据包没有事件。")
    return records


def make_case(
    evidence_dir: Path,
    case_dir: Path,
    case_id: str,
    seq: int,
    *,
    source_note: str | None = None,
    expect_text: Sequence[str] = (),
    forbid_tool: Sequence[str] = (),
) -> dict[str, str]:
    """从证据包生成四件样本并写出；返回每个文件的位置。"""
    records = load_events(evidence_dir)
    chosen = _chosen(records, seq)
    source = {"thread_id": chosen["source"]["thread_id"], "seq": chosen["source"]["seq"]}
    behavior = list(expect_text)
    failure = None
    if behavior:
        if any(not text.strip() for text in behavior):
            raise ReplayError("--expect-text 不能是空串。")
    else:
        failure = _failure_kind(chosen)
        if failure is None:
            raise ReplayError(
                f"序号 {seq} 不是被拒绝的操作、出错的结果或没有结局的回合；"
                "要提升一段行为，请给出 --expect-text。"
            )
    where = _relative(case_dir, evidence_dir)
    created = datetime.now(UTC).isoformat(timespec="seconds")
    kind = "behavior" if behavior else "failure"
    if behavior:
        expectation = {
            "summary": "来源之后的模型文本包含期望的说法，这一回合里没有出现被禁止的工具调用。",
            "text_contains_any": behavior,
            "forbid_tool_calls": list(forbid_tool),
        }
        grader: dict[str, Any] = {
            "version": 1,
            "type": "model_text_contains_any",
            "source": source,
            "expect": {"type": chosen["type"]},
            "text_contains_any": behavior,
            "forbid_tool_calls": list(forbid_tool),
        }
    else:
        expectation = _expectation(chosen)
        grader = _grader(chosen, source)
    files: dict[str, dict[str, Any]] = {
        "input.json": {
            "case_id": case_id,
            "created": created,
            "kind": kind,
            "source_note": source_note or f"证据包 {where}",
        },
        "expected.json": {
            "case_id": case_id,
            "kind": kind,
            "source": source,
            **({"failure_kind": failure} if failure is not None else {}),
            "expectation": expectation,
        },
        "grader.json": grader,
        "evidence-links.json": {
            "evidence": {"directory": where, "events": EVENTS},
            "source": source,
            "turn_id": chosen["turn_id"],
        },
    }
    if case_dir.exists() and any(case_dir.iterdir()):
        raise ReplayError(f"样本目录已存在且有内容：{case_dir}")
    case_dir.mkdir(parents=True, exist_ok=False)
    written: dict[str, str] = {}
    for name in FILES:
        text = json.dumps(redact(files[name]), ensure_ascii=False, indent=2) + "\n"
        (case_dir / name).write_text(text, encoding="utf-8", newline="\n")
        written[name] = str(case_dir / name)
    return written


def redact(value: Any) -> Any:
    """递归地把本机绝对路径换成占位路径；样本进仓库时不带机器上的位置。"""
    if isinstance(value, str):
        text = _SPACED.sub(PLACEHOLDER, value)
        text = _UNC.sub(PLACEHOLDER, text)
        text = _WINDOWS.sub(PLACEHOLDER, text)
        return _POSIX.sub(PLACEHOLDER, text)
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, dict):
        return {key: redact(item) for key, item in value.items()}
    return value


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--evidence-dir", type=Path, required=True, help="导出的证据包目录")
    parser.add_argument(
        "--case-dir", type=Path, required=True, help="回放样本的输出目录，必须还不存在"
    )
    parser.add_argument("--case-id", required=True, help="样本标识")
    parser.add_argument("--seq", type=int, required=True, help="要提升的证据事件序号")
    parser.add_argument("--source-note", help="这段事实从哪一次运行来的")
    parser.add_argument(
        "--expect-text",
        action="append",
        default=[],
        help="行为样本：来源之后的模型文本应包含的说法，可以重复",
    )
    parser.add_argument(
        "--forbid-tool",
        action="append",
        default=[],
        help="行为样本：这一回合里不得出现的工具，可以重复",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        written = make_case(
            args.evidence_dir,
            args.case_dir,
            args.case_id,
            args.seq,
            source_note=args.source_note,
            expect_text=args.expect_text,
            forbid_tool=args.forbid_tool,
        )
    except (OSError, ValueError) as exc:
        print(f"回放样本提升失败：{exc}", file=sys.stderr)
        return 2
    for name in FILES:
        print(f"已写出 {written[name]}")
    return 0


def _chosen(records: Sequence[dict[str, Any]], seq: int) -> dict[str, Any]:
    for record in records:
        if record["source"].get("seq") == seq:
            return record
    raise ReplayError(f"证据包里没有序号 {seq}。")


def _failure_kind(record: dict[str, Any]) -> str | None:
    """这一项算哪一种失败；不是失败时返回 None。"""
    if record["type"] == "approval" and record.get("decision") == "rejected":
        return "rejected_operation"
    if record["type"] == "tool_result" and bool(record.get("error")):
        return "tool_or_command_error"
    if record["type"] == "turn_end" and record.get("outcome") in {"cancelled", "interrupted"}:
        return "uncompleted_turn"
    return None


def _expectation(record: dict[str, Any]) -> dict[str, Any]:
    kind = _failure_kind(record)
    if kind == "rejected_operation":
        return {
            "summary": "被拒绝的操作没有执行，也不得为同一个目标换一个工具再试。",
            "operation": {"name": record["name"], "arguments": record["arguments"]},
        }
    if kind == "tool_or_command_error":
        return {
            "summary": "失败作为工具结果保留，并指向同一次调用。",
            "call_id": record["call_id"],
        }
    return {
        "summary": "没有正常完成的回合要能从事实里看出来。",
        "outcome": record["outcome"],
        "reason": record["reason"],
    }


def _grader(record: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    if record["type"] == "approval" and record.get("name") == "write_file":
        kind = "rejected_write_not_retried"
    else:
        kind = "evidence_event"
    expect: dict[str, Any] = {"type": record["type"]}
    for field in ("decision", "error", "outcome"):
        if field in record:
            expect[field] = record[field]
    return {"version": 1, "type": kind, "source": source, "expect": expect}


def _relative(case_dir: Path, evidence_dir: Path) -> str:
    """样本指向证据包的相对位置；写不出相对位置时就不提升，免得把本机路径带进仓库。"""
    try:
        return os.path.relpath(evidence_dir, case_dir).replace(os.sep, "/")
    except ValueError as exc:
        raise ReplayError("样本目录和证据包不在同一个盘上，写不出相对位置。") from exc


if __name__ == "__main__":
    raise SystemExit(main())
