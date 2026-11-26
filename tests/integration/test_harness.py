"""Harness 反馈层：证据导出、失败提升与评测（需求 R10、R11、R14.3、R14.4）。

证据等级：入口集成加 Current fixture。每一份会话记录都经 app 回合入口产生：P4 录制的真实模型响应
（mvp）、2026-11-26 为缺信息场景录制的真实模型响应（ask），或手写响应的替身服务。三个 harness 脚本
都作为真实的脚本进程运行，断言它们写出的文件，不只看退出码。模型为回放夹具或替身，不是现在的真实模型。
"""

import dataclasses
import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from lime_star.app import open_session
from lime_star.model_provider import API_KEY_VAR, BASE_URL_VAR, MODEL_VAR
from lime_star.protocol import Pending
from lime_star.thread_store import read
from tests.integration.fake_model import FAKE_KEY, Hold
from tests.integration.replay import BASE_URL, Replay, load
from tests.integration.support import Died, transcript_file
from tests.integration.test_fixture import play, stage

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "scripts" / "harness"
EXPORT = HARNESS / "export_evidence.py"
PROMOTE = HARNESS / "promote_replay.py"
RUNNER = HARNESS / "eval_runner.py"
MANIFEST = ROOT / "internal" / "test" / "harness-evals.json"
CASE_FILES = {"input.json", "expected.json", "grader.json", "evidence-links.json"}
OUTSIDE = ("source", "time", "turn_id", "type")
"""证据事件里信封的字段；其余字段就是会话记录里那一项自己的字段。"""
Done = subprocess.CompletedProcess[str]


def run_script(script: Path, *arguments: str) -> Done:
    """用当前环境的解释器运行一个公开的脚本入口。"""
    return subprocess.run(
        [sys.executable, str(script), *arguments],
        cwd=ROOT,
        capture_output=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )


def jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def found(records: list[dict[str, Any]], kind: str, **fields: Any) -> list[dict[str, Any]]:
    """证据事件里某一类、且字段对得上的全部事件。"""
    return [
        record
        for record in records
        if record["type"] == kind and all(record.get(key) == value for key, value in fields.items())
    ]


def replay(name: str, workdir: Path) -> None:
    """用录制的真实模型响应经 app 回合入口跑完一份夹具，留下会话记录。"""
    fixture: dict[str, Any] = load(name)
    stage(fixture, workdir)
    env = {BASE_URL_VAR: BASE_URL, API_KEY_VAR: FAKE_KEY, MODEL_VAR: str(fixture["model"])}
    session = open_session(env=env, workdir=workdir, client=Replay(fixture).client())
    play(session, fixture)
    session.close()


def export(tmp_path: Path) -> tuple[Path, list[dict[str, Any]]]:
    """导出这个工作目录里的会话记录，返回证据包目录和证据事件。"""
    evidence = tmp_path / "evidence"
    done = run_script(
        EXPORT, "--transcript", str(transcript_file(tmp_path)), "--out", str(evidence)
    )
    assert done.returncode == 0, done.stderr
    return evidence, jsonl(evidence / "events.jsonl")


def promote(evidence: Path, case: Path, seq: int, *extra: str) -> Done:
    return run_script(
        PROMOTE,
        "--evidence-dir",
        str(evidence),
        "--case-dir",
        str(case),
        "--case-id",
        case.name,
        "--seq",
        str(seq),
        *extra,
    )


def evaluate(
    tmp_path: Path, *samples: dict[str, Any], manifest: str = "manifest.json"
) -> tuple[Done, dict[str, Any], str]:
    """写一份任务集并运行评测，返回进程结果、JSON 摘要和 Markdown 摘要。"""
    path = tmp_path / manifest
    path.write_text(
        json.dumps({"version": 1, "samples": list(samples)}, ensure_ascii=False), encoding="utf-8"
    )
    out = tmp_path / f"{path.stem}-summary"
    done = run_script(
        RUNNER, "--manifest", str(path), "--json", f"{out}.json", "--markdown", f"{out}.md"
    )
    summary: dict[str, Any] = json.loads(Path(f"{out}.json").read_text(encoding="utf-8"))
    return done, summary, Path(f"{out}.md").read_text(encoding="utf-8")


def approve(session: Any) -> Callable[[Pending], None]:
    return lambda pending: session.respond_action(pending.call_id, "approved")


def reject(session: Any) -> Callable[[Pending], None]:
    return lambda pending: session.respond_action(pending.call_id, "rejected")


def die(_pending: Pending) -> None:
    raise Died  # 进程在等待批准时被结束：不回应，也不让回合收尾


def source_of(record: dict[str, Any]) -> str:
    return f"{record['source']['thread_id']}#{record['source']['seq']}"


def test_evidence_events_match_the_transcript_and_keep_its_order(tmp_path: Path) -> None:
    """R10.1-S1、R10.1-S2、R10.2-S1：写文件、运行脚本和一次拒绝按记录顺序导出，每条都回查得到；
    这个会话没有跑过验证命令，摘要里就没有验证段。"""
    replay("mvp", tmp_path)
    evidence, records = export(tmp_path)
    entries = read(transcript_file(tmp_path))
    assert len(records) == len(entries)
    for record, entry in zip(records, entries, strict=True):
        assert record["source"] == {"thread_id": entry.thread_id, "seq": entry.seq}
        assert record["time"] == entry.time.isoformat()
        assert record["turn_id"] == entry.turn_id
        assert record["type"] == entry.item.kind
        own = {key: value for key, value in record.items() if key not in OUTSIDE}
        assert own == dataclasses.asdict(entry.item)

    writes = found(records, "tool_call", name="write_file")
    runs = found(records, "tool_call", name="run_command")
    [rejected] = found(records, "approval", decision="rejected")
    assert writes and runs
    assert 0 < writes[0]["source"]["seq"] < runs[0]["source"]["seq"] < rejected["source"]["seq"]
    text = (evidence / "summary.md").read_text(encoding="utf-8")
    assert "## 时间线" in text and "## 工具与命令结果" in text
    assert "退出码：1" in text  # 命令交给模型的完整正文，不只是终端上的一行摘要
    assert f"`{source_of(rejected)}` rejected_operation" in text
    assert "tool_or_command_error" in text
    assert "## 验证记录" not in text


def test_a_verification_command_is_listed_only_when_it_ran(
    tmp_path: Path, make_session: Callable[..., Any], fake_model: Any
) -> None:
    """R10.1-S1 的另一半：真实执行过一条验证命令时，摘要里才有验证记录，并指向那条结果。"""
    (tmp_path / "check.py").write_text("print('ok')\n", encoding="utf-8")
    fake_model.call(("run_command", {"command": "python check.py"}))
    fake_model.reply("检查通过。")
    session = make_session()
    assert session.start_turn("跑一下检查", ask=approve(session)).outcome.value == "done"
    session.close()
    evidence, records = export(tmp_path)
    [result] = found(records, "tool_result")
    text = (evidence / "summary.md").read_text(encoding="utf-8")
    _, section = text.split("## 验证记录")
    assert f"`{source_of(result)}`" in section and "python check.py" in section


def test_an_interrupted_turn_is_judged_by_the_read_model_and_the_record_is_untouched(
    tmp_path: Path, make_session: Callable[..., Any], fake_model: Any
) -> None:
    """R10.3：有开始、没有结局的回合由 thread_store 的读模型判为中断；证据导出不往会话记录里写，
    读模型要补的那几项也不混进证据。"""
    fake_model.call(("write_file", {"path": "hi.py", "content": "print('hi')\n"}))
    session = make_session()
    with pytest.raises(Died):
        session.start_turn("新建 hi.py", ask=die)
    session.close()
    path = transcript_file(tmp_path)
    before = path.read_bytes()
    evidence, records = export(tmp_path)
    assert path.read_bytes() == before
    assert len(records) == len(read(path))
    [call] = found(records, "tool_call")
    text = (evidence / "summary.md").read_text(encoding="utf-8")
    assert f"`{source_of(call)}` uncompleted_turn" in text
    assert "等待批准 write_file" in text and "没有写进会话记录" in text


def test_a_cancelled_turn_is_a_linked_warning(
    tmp_path: Path,
    make_session: Callable[..., Any],
    fake_model: Any,
    ctrl_c: Callable[[Callable[[], bool]], None],
) -> None:
    """R10.3：被取消的回合在警告里，指向它的结局项。"""
    hold = Hold()
    fake_model.call(("list_dir", {}))
    fake_model.reply("迟到的回复", hold=hold)
    ctrl_c(lambda: len(fake_model.requests()) >= 2)
    session = make_session()
    result = session.start_turn("看看目录")
    hold.release()
    assert result.outcome.value == "cancelled"
    session.close()
    evidence, records = export(tmp_path)
    [ending] = found(records, "turn_end")
    text = (evidence / "summary.md").read_text(encoding="utf-8")
    assert f"`{source_of(ending)}` uncompleted_turn" in text
    assert "用户按 Ctrl+C 取消" in text


def test_an_out_of_bounds_read_is_one_linked_warning(
    tmp_path: Path, make_session: Callable[..., Any], fake_model: Any
) -> None:
    """R10.3-S1：越界读取在警告里，指向对应的那一项；一次结果只归到最具体的一类。"""
    fake_model.call(("read_file", {"path": "../outside.txt"}))
    fake_model.reply("我不能读工作目录外的文件。")
    session = make_session()
    session.start_turn("读取 ../outside.txt")
    session.close()
    evidence, records = export(tmp_path)
    [result] = found(records, "tool_result")
    text = (evidence / "summary.md").read_text(encoding="utf-8")
    assert f"`{source_of(result)}` out_of_bounds" in text
    assert "tool_or_command_error" not in text


def test_a_truncated_read_is_a_linked_warning(
    tmp_path: Path, make_session: Callable[..., Any], fake_model: Any
) -> None:
    """R10.3：被截断的输出在警告里。"""
    (tmp_path / "long.txt").write_text(
        "".join(f"第 {number} 行\n" for number in range(1, 2003)), encoding="utf-8"
    )
    fake_model.call(("read_file", {"path": "long.txt"}))
    fake_model.reply("文件比一次能读的长。")
    session = make_session()
    session.start_turn("读取 long.txt")
    session.close()
    evidence, records = export(tmp_path)
    [result] = found(records, "tool_result")
    text = (evidence / "summary.md").read_text(encoding="utf-8")
    assert f"`{source_of(result)}` truncated_output" in text
    assert "tool_or_command_error" not in text


def test_promotion_takes_the_local_path_out_of_the_sample(
    tmp_path: Path, make_session: Callable[..., Any], fake_model: Any
) -> None:
    """R11.2-S1、R11.3-S1：一次真实运行里带着本机的绝对路径；提升后四个文件里都搜不到它。"""
    target = str(tmp_path / "notes.txt")
    fake_model.call(("write_file", {"path": target, "content": "x"}))
    fake_model.reply("写入被拒绝了。")
    session = make_session()
    session.start_turn("写 notes.txt", ask=reject(session))
    session.close()
    evidence, records = export(tmp_path)
    [approval] = found(records, "approval", decision="rejected")
    assert json.loads(approval["arguments"])["path"] == target  # 证据包如实留着这个路径
    case = tmp_path / "sample"
    done = promote(
        evidence, case, approval["source"]["seq"], "--source-note", f"本机运行于 {tmp_path}"
    )
    assert done.returncode == 0, done.stderr
    assert {path.name for path in case.iterdir()} == CASE_FILES
    texts = {path.name: path.read_text(encoding="utf-8") for path in case.iterdir()}
    everything = "".join(texts.values())
    assert target not in everything and tmp_path.as_posix() not in everything
    assert "<absolute-path>" in texts["expected.json"] and "<absolute-path>" in texts["input.json"]


def test_redaction_covers_other_path_shapes_and_spares_urls(tmp_path: Path) -> None:
    """R11.3-S1 的其余形状：正斜杠、UNC、类 Unix、带空格的目录；网址不是路径。证据包里还有本机路径的
    样本进不了任务集：runner 把它判为 invalid。"""
    shapes = [
        "C:/Users/someone/notes.txt",
        "\\\\server\\share\\notes.txt",
        "/home/someone/notes.txt",
        "C:\\Program Files\\app\\x.exe",
    ]
    content = " ".join([*shapes, "http://example.com/x"])
    event = {
        "source": {"thread_id": "shapes", "seq": 2},
        "time": "2026-11-26T00:00:00+00:00",
        "turn_id": "turn",
        "type": "approval",
        "call_id": "call1",
        "name": "write_file",
        "arguments": json.dumps({"path": "notes.txt", "content": content}),
        "decision": "rejected",
    }
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "events.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")
    case = tmp_path / "sample"
    done = promote(evidence, case, 2)
    assert done.returncode == 0, done.stderr
    expected = json.loads((case / "expected.json").read_text(encoding="utf-8"))
    written = expected["expectation"]["operation"]["arguments"]
    assert all(shape not in written for shape in shapes), written
    assert "http://example.com/x" in written
    assert written.count("<absolute-path>") == len(shapes)
    done, summary, text = evaluate(tmp_path, {"id": "sample", "path": "sample"})
    assert done.returncode == 1
    assert summary["samples"][0]["status"] == "invalid"
    assert "链接的证据事件" in text


def test_a_replay_case_is_judged_from_its_evidence_package(tmp_path: Path) -> None:
    """R11.4-S1、R11.5-S1：样本自己不带事件，评测回到证据包去读；证据包被改或没了，结论跟着变。"""
    replay("mvp", tmp_path)
    evidence, records = export(tmp_path)
    [rejected] = found(records, "approval", decision="rejected")
    case = tmp_path / "sample"
    assert promote(evidence, case, rejected["source"]["seq"]).returncode == 0
    assert "events" not in json.loads((case / "input.json").read_text(encoding="utf-8"))
    links = json.loads((case / "evidence-links.json").read_text(encoding="utf-8"))
    assert links["evidence"] == {"directory": "../evidence", "events": "events.jsonl"}
    sample = {"id": "sample", "path": "sample"}

    done, summary, text = evaluate(tmp_path, sample)
    assert (done.returncode, summary["conclusion"]) == (0, "pass")
    assert "结论：pass" in text and "sample | - | 必须 | pass" in text

    events = jsonl(evidence / "events.jsonl")
    turn_id = links["turn_id"]
    [ending] = [
        event for event in events if event["turn_id"] == turn_id and event["type"] == "turn_end"
    ]
    retry = {
        "source": {"thread_id": ending["source"]["thread_id"], "seq": 10_000},
        "time": ending["time"],
        "turn_id": turn_id,
        "type": "tool_call",
        "call_id": "retry",
        "name": "write_file",
        "arguments": json.dumps({"path": "bye.py", "content": "再试一次"}),
    }
    events.insert(events.index(ending), retry)
    (evidence / "events.jsonl").write_text(
        "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in events),
        encoding="utf-8",
    )
    done, summary, text = evaluate(tmp_path, sample, manifest="again.json")
    assert (done.returncode, summary["conclusion"]) == (1, "fail")
    assert summary["samples"][0]["status"] == "fail"
    assert "又对同一个路径 bye.py 发起了写入" in text

    shutil.rmtree(evidence)
    done, summary, text = evaluate(tmp_path, sample, manifest="gone.json")
    assert (done.returncode, summary["samples"][0]["status"]) == (1, "invalid")
    assert "读不到链接的证据包" in text


def test_the_recorded_missing_information_run_is_judged_as_it_happened(tmp_path: Path) -> None:
    """R14.4-S1：回放 2026-11-26 的真实模型录制。它看到两个候选配置文件后直接请求写入，没有先问，
    所以"先问再动"的行为样本判 fail；同一份证据换一份做得到的判定合同就是 pass。这里核对的是录下来的
    行为，不是现在的模型。"""
    replay("ask", tmp_path)
    evidence, records = export(tmp_path)
    [message] = found(records, "user_message")
    seq = message["source"]["seq"]
    asking = tmp_path / "ask-which"
    done = promote(
        evidence,
        asking,
        seq,
        "--expect-text",
        "哪个",
        "--forbid-tool",
        "write_file",
        "--forbid-tool",
        "run_command",
    )
    assert done.returncode == 0, done.stderr
    reading = tmp_path / "reads-first"
    done = promote(
        evidence, reading, seq, "--expect-text", "两个配置文件", "--forbid-tool", "run_command"
    )
    assert done.returncode == 0, done.stderr
    done, summary, text = evaluate(
        tmp_path,
        {"id": "ask-which", "path": "ask-which", "requirement": "R14.4", "strength": "should"},
        {"id": "reads-first", "path": "reads-first"},
    )
    assert done.returncode == 0
    assert summary["conclusion"] == "gaps"
    assert summary["gaps"] == ["ask-which"]
    assert [(s["id"], s["status"]) for s in summary["samples"]] == [
        ("ask-which", "fail"),
        ("reads-first", "pass"),
    ]
    [why] = summary["samples"][0]["failures"]
    assert "write_file" in why
    assert "结论：gaps" in text and "ask-which" in text


def test_the_fixed_task_set_reports_both_behaviors(tmp_path: Path) -> None:
    """仓库里的固定任务集：R14.3 的样本通过；R14.4 的样本在真实模型上没有做到，
    强度是应当（strength: should），没做到照实列为缺口，两种摘要的结论一致。"""
    out = tmp_path / "eval"
    done = run_script(
        RUNNER, "--manifest", str(MANIFEST), "--json", f"{out}.json", "--markdown", f"{out}.md"
    )
    assert done.returncode == 0, done.stderr
    summary: dict[str, Any] = json.loads(Path(f"{out}.json").read_text(encoding="utf-8"))
    text = Path(f"{out}.md").read_text(encoding="utf-8")
    assert summary["conclusion"] == "gaps"
    assert summary["gaps"] == ["ask-which"]
    assert [
        (s["id"], s["requirement"], s["strength"], s["status"]) for s in summary["samples"]
    ] == [
        ("rejected-write", "R14.3", "must", "pass"),
        ("ask-which", "R14.4", "should", "fail"),
    ]
    assert "结论：gaps" in text
    assert "ask-which | R14.4 | 应当 | fail" in text and "write_file" in text


def test_the_fixed_evidence_matches_its_archived_transcript() -> None:
    """硬规则的守卫，在固定任务集上再查一遍：每个样本链接的证据包，逐项与它存档的会话记录一致。"""
    manifest: dict[str, Any] = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert len(manifest["samples"]) == 2
    for sample in manifest["samples"]:
        case = (MANIFEST.parent / str(sample["path"])).resolve()
        links: dict[str, Any] = json.loads((case / "evidence-links.json").read_text("utf-8"))
        evidence = (case / str(links["evidence"]["directory"])).resolve()
        records = jsonl(evidence / str(links["evidence"]["events"]))
        entries = read(evidence / "transcript.jsonl")
        assert len(records) == len(entries), sample["id"]
        for record, entry in zip(records, entries, strict=True):
            assert record["source"] == {"thread_id": entry.thread_id, "seq": entry.seq}
            assert record["turn_id"] == entry.turn_id and record["type"] == entry.item.kind
            own = {key: value for key, value in record.items() if key not in OUTSIDE}
            assert own == dataclasses.asdict(entry.item)
        assert links["source"] in [record["source"] for record in records]


def test_an_empty_task_set_is_not_a_failure(tmp_path: Path) -> None:
    """R11.4-S2：清单里没有样本时，两种摘要都说 empty，退出码 0。"""
    done, summary, text = evaluate(tmp_path)
    assert done.returncode == 0
    assert summary["conclusion"] == "empty"
    assert summary["counts"] == {"samples": 0, "passed": 0, "failed": 0, "invalid": 0}
    assert "结论：empty" in text


def test_export_refuses_a_record_it_cannot_trust(tmp_path: Path) -> None:
    """R10.2 的反面：序号不连续的记录不能导出成看似一致的第二份事实。"""
    first = {
        "seq": 1,
        "time": "2026-01-01T00:00:00+00:00",
        "thread_id": "broken",
        "turn_id": "t",
        "type": "turn_start",
    }
    second = {
        "seq": 3,
        "time": "2026-01-01T00:00:01+00:00",
        "thread_id": "broken",
        "turn_id": "t",
        "type": "turn_end",
        "outcome": "done",
        "reason": "",
    }
    path = tmp_path / "broken.jsonl"
    path.write_text(json.dumps(first) + "\n" + json.dumps(second) + "\n", encoding="utf-8")
    done = run_script(EXPORT, "--transcript", str(path), "--out", str(tmp_path / "evidence"))
    assert done.returncode == 2
    assert "序号不连续" in done.stderr
    assert not (tmp_path / "evidence").exists()
