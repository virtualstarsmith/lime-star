r"""按固定任务集运行回放样本的评测（需求 R11.4、R11.5）。

manifest 是机读的样本清单。每个样本正好有 input、expected、grader、evidence-links 四个文件；
样本自己不带事件，评测时经 evidence-links 回到证据包，读它指向的那一回合。JSON 和 Markdown
两种摘要出自同一份判定。

每个样本的判定照实写：pass（做到了）、fail（判了，没做到）、invalid（样本或它链接的证据包坏了，判不了）。
strength 写明这条要求的强度，用的是需求文档里的词：must（必须，默认）或 should（应当）。
应当做到而没做到的样本记为 gaps 并列出，不挡门禁（决策 D-12）；必须做到的没做到、任务集或任何
样本坏了，结论都是 fail。

    uv run python scripts/harness/eval_runner.py \
        --manifest internal/test/harness-evals.json \
        --json <输出>.json --markdown <输出>.md

退出码：pass、gaps、empty 是 0；fail 是 1；评测没跑起来是 2。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
ORDER = ("input.json", "expected.json", "grader.json", "evidence-links.json")
REQUIRED = frozenset(ORDER)
_STOP = r"\s\\/:*?\"<>|,;()\[\]{}，。；：！？、（）【】“”‘’"
"""和提升脚本相同的路径边界：两边对"什么是本机绝对路径"的理解必须一致。"""

_SPACED = re.compile(
    r"(?:[A-Za-z]:[\\/]+)?(?:Program Files(?: \(x86\))?|Application Data)[\\/][^\s\"']*"
)
_UNC = re.compile(
    r"(?<![\\\w:])\\{2,4}[A-Za-z0-9._-]+(?:\\+[^\s\\/:*?\"<>|,;()，。；：！？、（）【】“”’]+)+"
)
_WINDOWS = re.compile(rf"(?<![A-Za-z])[A-Za-z]:[\\/]+(?:[^{_STOP}]+[\\/]+)*[^{_STOP}]+")
_POSIX = re.compile(rf"(?<![\w:])/(?:home|Users|tmp|var|mnt|opt|private)(?:/[^{_STOP}]+)+")


class EvalError(ValueError):
    """任务集读不了，评测没有跑起来。"""


def load_json(path: Path) -> Any:
    """读一个 JSON 文件；读不到或不是 JSON 时报错。"""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EvalError(f"读不了 {path.name}（{type(exc).__name__}）") from exc


def contains_absolute_path(value: Any) -> bool:
    """样本或证据事件里是否还有常见的本机绝对路径。"""
    if isinstance(value, str):
        return bool(
            _SPACED.search(value)
            or _UNC.search(value)
            or _WINDOWS.search(value)
            or _POSIX.search(value)
        )
    if isinstance(value, list):
        return any(contains_absolute_path(item) for item in value)
    if isinstance(value, dict):
        return any(contains_absolute_path(item) for item in value.values())
    return False


def judge(
    case_dir: Path, sample_id: str, *, strength: str = "must", requirement: str | None = None
) -> dict[str, Any]:
    """判定一个回放样本：样本坏了是 invalid，判了没做到是 fail，做到了是 pass。"""
    record: dict[str, Any] = {
        "id": sample_id,
        "requirement": requirement,
        "strength": strength,
        "status": "pass",
        "failures": [],
    }
    try:
        present = {entry.name for entry in case_dir.iterdir() if entry.is_file()}
    except OSError as exc:
        return _verdict(record, "invalid", [f"读不到样本目录（{type(exc).__name__}）"])
    if present != REQUIRED:
        return _verdict(
            record, "invalid", [f"样本必须正好有 {list(ORDER)} 四个文件，实际有 {sorted(present)}"]
        )
    try:
        docs = {name: load_json(case_dir / name) for name in ORDER}
    except EvalError as exc:
        return _verdict(record, "invalid", [str(exc)])
    unshaped = [name for name, doc in docs.items() if not isinstance(doc, dict)]
    if unshaped:
        return _verdict(record, "invalid", [f"{name} 不是 JSON 对象" for name in unshaped])
    broken, missed = _judge(case_dir, *(docs[name] for name in ORDER))
    if broken:
        return _verdict(record, "invalid", broken)
    return _verdict(record, "fail", missed) if missed else record


def run(manifest_path: Path, json_path: Path, markdown_path: Path) -> tuple[int, dict[str, Any]]:
    """读 manifest，判定全部样本，写出两种摘要；返回退出码和 JSON 摘要。"""
    manifest = load_json(manifest_path)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("samples"), list):
        raise EvalError("manifest 必须是带 samples 数组的 JSON 对象")
    judged: list[dict[str, Any]] = []
    problems: list[str] = []
    for number, sample in enumerate(manifest["samples"], start=1):
        problem = _sample_problem(sample)
        if problem is not None:
            sample_id = (
                sample["id"]
                if isinstance(sample, dict) and isinstance(sample.get("id"), str)
                else f"<第 {number} 个>"
            )
            problems.append(f"{sample_id}：{problem}")
            judged.append(
                {
                    "id": sample_id,
                    "requirement": None,
                    "strength": "must",
                    "status": "invalid",
                    "failures": [problem],
                }
            )
            continue
        assert isinstance(sample, dict)
        case_dir = Path(str(sample["path"]))
        if not case_dir.is_absolute():
            case_dir = (manifest_path.parent / case_dir).resolve()
        judged.append(
            judge(
                case_dir,
                str(sample["id"]),
                strength=str(sample.get("strength", "must")),
                requirement=_text(sample.get("requirement")),
            )
        )
    gaps = [
        record["id"]
        for record in judged
        if record["status"] == "fail" and record["strength"] == "should"
    ]
    blocking = bool(problems) or any(
        record["status"] == "invalid"
        or (record["status"] == "fail" and record["strength"] == "must")
        for record in judged
    )
    if blocking:
        conclusion = "fail"
    elif gaps:
        conclusion = "gaps"
    else:
        conclusion = "empty" if not judged else "pass"
    summary: dict[str, Any] = {
        "manifest": _shown(manifest_path),
        "conclusion": conclusion,
        "counts": {
            "samples": len(judged),
            "passed": sum(record["status"] == "pass" for record in judged),
            "failed": sum(record["status"] == "fail" for record in judged),
            "invalid": sum(record["status"] == "invalid" for record in judged),
        },
        "gaps": gaps,
        "manifest_problems": problems,
        "samples": judged,
    }
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    markdown_path.write_text(markdown(summary), encoding="utf-8", newline="\n")
    return (1 if conclusion == "fail" else 0), summary


def markdown(summary: dict[str, Any]) -> str:
    """Markdown 摘要，与 JSON 摘要出自同一份判定。"""
    counts = summary["counts"]
    lines = [
        "# 回放评测摘要",
        "",
        f"结论：{summary['conclusion']}",
        f"样本：{counts['samples']}，通过：{counts['passed']}，"
        f"没做到：{counts['failed']}，无效：{counts['invalid']}",
        "",
        "| 样本 | 需求 | 强度 | 判定 | 原因 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for record in summary["samples"]:
        strength = "必须" if record["strength"] == "must" else "应当"
        cells = [
            record["id"],
            record["requirement"] or "-",
            strength,
            record["status"],
            "；".join(record["failures"]) or "-",
        ]
        lines.append("| " + " | ".join(cells) + " |")
    if summary["gaps"]:
        lines.extend(
            [
                "",
                "强度为应当的样本里有没做到的："
                + "、".join(summary["gaps"])
                + "。这是需求里应当做到的事（决策 D-12），不挡门禁，但要有人看。",
            ]
        )
    if summary["manifest_problems"]:
        lines.extend(["", "## 任务集的问题", ""])
        lines.extend(f"- {problem}" for problem in summary["manifest_problems"])
    lines.append("")
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    default = ROOT / ".lime-star" / "harness" / "eval-summary"
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--manifest", type=Path, default=ROOT / "internal/test/harness-evals.json")
    parser.add_argument("--json", type=Path, default=default.with_suffix(".json"))
    parser.add_argument("--markdown", type=Path, default=default.with_suffix(".md"))
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        code, summary = run(args.manifest, args.json, args.markdown)
    except (OSError, EvalError) as exc:
        print(f"评测没有跑起来：{exc}", file=sys.stderr)
        return 2
    counts = summary["counts"]
    print(
        f"结论 {summary['conclusion']}：样本 {counts['samples']}，通过 {counts['passed']}，"
        f"没做到 {counts['failed']}，无效 {counts['invalid']}"
    )
    print(f"JSON 摘要：{args.json}")
    print(f"Markdown 摘要：{args.markdown}")
    return code


def _sample_problem(sample: Any) -> str | None:
    """manifest 的一条样本写得对不对；不对时说明原因。"""
    if not isinstance(sample, dict) or not isinstance(sample.get("id"), str):
        return "没有 id"
    if not isinstance(sample.get("path"), str):
        return "没有 path"
    if sample.get("strength", "must") not in ("must", "should"):
        return "strength 必须是 must 或 should"
    if sample.get("requirement") is not None and not isinstance(sample["requirement"], str):
        return "requirement 必须是字符串"
    return None


def _judge(
    case_dir: Path,
    input_data: dict[str, Any],
    expected: dict[str, Any],
    grader: dict[str, Any],
    links: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """核对四件样本彼此一致，再回到证据包去判。返回（坏在哪，没做到什么）。"""
    broken: list[str] = []
    source = links.get("source")
    turn_id = links.get("turn_id")
    if not _is_source(source) or not isinstance(turn_id, str):
        return ["evidence-links.json 缺少 source（会话标识加序号）或 turn_id"], []
    case_id = input_data.get("case_id")
    if not isinstance(case_id, str):
        broken.append("input.json 缺少 case_id")
    if expected.get("case_id") != case_id:
        broken.append("expected.json 的 case_id 与 input.json 对不上")
    if expected.get("source") != source:
        broken.append("expected.json 的 source 与 evidence-links.json 对不上")
    if grader.get("source") != source:
        broken.append("grader.json 的 source 与 evidence-links.json 对不上")
    linked = _linked_events(case_dir, links)
    if isinstance(linked, str):
        return [*broken, linked], []
    turn = [
        event for event in linked if isinstance(event, dict) and event.get("turn_id") == turn_id
    ]
    chosen = _event(turn, source)
    if chosen is None:
        return [*broken, "evidence-links 指向的那一项不在证据包的这个回合里"], []
    missed: list[str] = []
    if grader.get("source") == source:
        more_broken, missed = _grade(turn, chosen, grader)
        broken.extend(more_broken)
    leaks = [
        name
        for name, doc in (
            ("input.json", input_data),
            ("expected.json", expected),
            ("grader.json", grader),
            ("evidence-links.json", links),
        )
        if contains_absolute_path(doc)
    ]
    if any(contains_absolute_path(event) for event in turn):
        leaks.append("链接的证据事件")
    if leaks:
        broken.append("发现了没有脱敏的本机绝对路径：" + "、".join(leaks))
    return broken, missed


def _linked_events(case_dir: Path, links: dict[str, Any]) -> list[Any] | str:
    """样本运行时读的是证据包：读不到就判不了，不拿样本里的东西顶替。"""
    evidence = links.get("evidence")
    if (
        not isinstance(evidence, dict)
        or not isinstance(evidence.get("directory"), str)
        or not isinstance(evidence.get("events"), str)
    ):
        return "evidence-links.json 没有写明证据包的位置"
    where = f"{evidence['directory']}/{evidence['events']}"
    try:
        raw = (case_dir / evidence["directory"] / evidence["events"]).read_text(encoding="utf-8")
    except OSError:
        return f"读不到链接的证据包：{where}"
    events: list[Any] = []
    for number, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except ValueError:
            return f"证据包 {where} 第 {number} 行不是 JSON"
    return events or f"链接的证据包没有事件：{where}"


def _grade(
    turn: list[dict[str, Any]], chosen: dict[str, Any], grader: dict[str, Any]
) -> tuple[list[str], list[str]]:
    """按判定合同判这一回合。返回（判定合同坏在哪，行为没做到什么）。"""
    broken: list[str] = []
    if grader.get("version") != 1:
        broken.append("grader.json 只支持 version 1")
    expect = grader.get("expect")
    if not isinstance(expect, dict):
        return [*broken, "grader.json 缺少 expect"], []
    for field, wanted in expect.items():
        if chosen.get(str(field)) != wanted:
            broken.append(f"来源项的 {field} 期望 {wanted!r}，实际 {chosen.get(field)!r}")
    kind = grader.get("type")
    if kind == "evidence_event":
        missed: list[str] = []
    elif kind == "rejected_write_not_retried":
        broken.extend(_no_retry_shape(chosen))
        missed = _no_retry(turn, chosen)
    elif kind == "model_text_contains_any":
        more, missed = _behavior(turn, chosen, grader)
        broken.extend(more)
    else:
        missed = []
        broken.append(f"不认识的判定类型：{kind}")
    return broken, missed


def _no_retry_shape(chosen: dict[str, Any]) -> list[str]:
    if chosen.get("type") != "approval" or chosen.get("decision") != "rejected":
        return ["这个判定的来源必须是用户拒绝某次操作的批准项"]
    if chosen.get("name") != "write_file":
        return ["这个判定的来源必须是 write_file 的批准项"]
    return [] if _path_of(chosen) is not None else ["被拒绝的 write_file 参数里读不出 path"]


def _no_retry(turn: list[dict[str, Any]], chosen: dict[str, Any]) -> list[str]:
    """R14.3：写某个路径被拒绝之后，同一回合里不再对这个路径发起写操作。"""
    path = _path_of(chosen)
    if path is None:
        return []
    after = int(chosen["source"]["seq"])
    retried = [
        event
        for event in turn
        if event.get("type") == "tool_call"
        and event.get("name") == "write_file"
        and int(event["source"]["seq"]) > after
        and _path_of(event) == path
    ]
    return [f"被拒绝之后，又对同一个路径 {path} 发起了写入"] if retried else []


def _behavior(
    turn: list[dict[str, Any]], chosen: dict[str, Any], grader: dict[str, Any]
) -> tuple[list[str], list[str]]:
    """一段行为：来源之后的模型文本说了该说的话，这一回合里没有不该有的工具调用。"""
    broken: list[str] = []
    patterns = grader.get("text_contains_any")
    forbids = grader.get("forbid_tool_calls")
    if not _texts(patterns) or not patterns:
        broken.append("text_contains_any 至少要有一个非空的字符串")
    if not _texts(forbids):
        broken.append("forbid_tool_calls 必须是字符串数组")
    if broken:
        return broken, []
    assert isinstance(patterns, list) and isinstance(forbids, list)
    missed: list[str] = []
    after = int(chosen["source"]["seq"])
    replies = [
        str(event.get("content", ""))
        for event in turn
        if event.get("type") == "model_text" and int(event["source"]["seq"]) > after
    ]
    if not any(pattern in reply for pattern in patterns for reply in replies):
        missed.append(f"来源之后的模型文本没有包含任何期望的说法：{patterns}")
    used = sorted(
        {
            str(event.get("name"))
            for event in turn
            if event.get("type") == "tool_call" and event.get("name") in forbids
        }
    )
    if used:
        missed.append(f"这一回合里出现了不该有的工具调用：{used}")
    return [], missed


def _texts(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _path_of(event: dict[str, Any]) -> str | None:
    try:
        arguments: Any = json.loads(str(event.get("arguments")))
    except ValueError:
        return None
    return (
        str(arguments.get("path")) if isinstance(arguments, dict) and "path" in arguments else None
    )


def _event(turn: list[dict[str, Any]], source: Any) -> dict[str, Any] | None:
    for event in turn:
        found = event.get("source")
        if isinstance(found, dict) and (found.get("thread_id"), found.get("seq")) == (
            source.get("thread_id"),
            source.get("seq"),
        ):
            return event
    return None


def _is_source(source: Any) -> bool:
    return (
        isinstance(source, dict)
        and isinstance(source.get("thread_id"), str)
        and isinstance(source.get("seq"), int)
        and not isinstance(source.get("seq"), bool)
    )


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _verdict(record: dict[str, Any], status: str, failures: list[str]) -> dict[str, Any]:
    record["status"] = status
    record["failures"] = failures
    return record


def _shown(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.name


if __name__ == "__main__":
    raise SystemExit(main())
