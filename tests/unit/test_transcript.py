"""会话记录的单元测试：逐项落盘、只凭文件读回、八类项的往返、残行与看不懂的行（R6.5 到 R6.7）。

证据等级：Unit。它经 app 回合入口被写入和读回的场景在 tests/integration/test_transcript.py 里。
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from lime_star.protocol import (
    ENVELOPE,
    ITEM_KINDS,
    Approval,
    Entry,
    Item,
    ModelText,
    Outcome,
    Reasoning,
    ToolCall,
    ToolResult,
    TurnEnd,
    TurnStart,
    UserMessage,
)
from lime_star.thread_store import THREADS_DIR, BrokenItem, Transcript, decode, encode, read

WHEN = datetime(2026, 11, 25, 1, 2, 3, 400000, tzinfo=UTC)
WHEN_TEXT = "2026-11-25T01:02:03.400000+00:00"
EVERY_KIND: tuple[Item, ...] = (
    TurnStart(),
    UserMessage("读一下"),
    Reasoning("想一想"),
    ModelText("我看看"),
    ToolCall(call_id="c1", name="read_file", arguments='{"path": "a.txt"}'),
    Approval(call_id="c2", name="run_command", arguments='{"command": "ls"}', decision="rejected"),
    ToolResult(call_id="c1", content="     1  甲", summary="读到 1 行"),
    TurnEnd(outcome=Outcome.CANCELLED, reason="用户按 Ctrl+C 取消"),
)


def open_at(tmp_path: Path, thread_id: str = "thread-1") -> Transcript:
    return Transcript.at(tmp_path, thread_id, now=lambda: WHEN)


def line(**changes: object) -> dict[str, Any]:
    """一行合法的用户消息，按 changes 改写或删掉字段（值写成 ... 表示删掉）。"""
    record: dict[str, Any] = {
        "seq": 1,
        "time": WHEN_TEXT,
        "thread_id": "t",
        "turn_id": "u",
        "type": "user_message",
        "content": "你好",
    }
    for key, value in changes.items():
        if value is ...:
            record.pop(key)
        else:
            record[key] = value
    return record


def test_each_item_is_one_complete_line_under_the_workdir(tmp_path: Path) -> None:
    """决策 D-23、D-29：一个会话一个文件，放在工作目录下的 .lime-star/threads 里。

    第一项写入时文件才出现。
    """
    transcript = open_at(tmp_path)
    assert transcript.path == tmp_path / THREADS_DIR / "thread-1.jsonl"
    assert transcript.thread_id == "thread-1"
    assert (transcript.path.parent.is_dir(), transcript.path.exists()) == (True, False)
    first = transcript.append(UserMessage("你好"), "turn-1")
    end = transcript.append(TurnEnd(Outcome.DONE, ""), "turn-1")
    assert first == Entry(1, WHEN, "thread-1", "turn-1", UserMessage("你好"))
    assert end == Entry(2, WHEN, "thread-1", "turn-1", TurnEnd(Outcome.DONE, ""))
    raw = transcript.path.read_bytes()
    assert (raw.count(b"\n"), raw.endswith(b"\n")) == (2, True)
    assert json.loads(raw.split(b"\n")[0]) == line(thread_id="thread-1", turn_id="turn-1")
    assert "你好".encode() in raw  # 中文原样写出


def test_every_kind_round_trips(tmp_path: Path) -> None:
    """R6.6-S1（存储层）：八类项都能写进去，读回后按类型辨认，顺序和内容同写入时一致。"""
    transcript = open_at(tmp_path)
    written = tuple(transcript.append(item, "turn-1") for item in EVERY_KIND)
    assert sorted(entry.item.kind for entry in written) == sorted(kind.kind for kind in ITEM_KINDS)
    assert written == tuple(
        Entry(number, WHEN, "thread-1", "turn-1", item)
        for number, item in enumerate(EVERY_KIND, start=1)
    )
    assert read(transcript.path) == written
    assert Transcript(transcript.path, "thread-1").read() == written


def test_a_missing_file_reads_as_empty(tmp_path: Path) -> None:
    assert read(tmp_path / "nowhere.jsonl") == ()


def test_a_partial_last_line_is_not_an_item(tmp_path: Path) -> None:
    """R6.5-S1（读的一方）：十项之后拖着半行，读回完整的十项。

    半行切在多字节字符中间也一样。
    """
    path = tmp_path / "t.jsonl"
    path.write_bytes(b"".join(json.dumps(line(seq=n)).encode() + b"\n" for n in range(1, 11)))
    whole = read(path)
    assert [entry.seq for entry in whole] == list(range(1, 11))
    path.write_bytes(path.read_bytes() + '{"seq": 11, "content": "半'.encode()[:-1])
    assert read(path) == whole
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(BrokenItem):
        read(path)


def test_appending_goes_on_where_the_file_ends(tmp_path: Path) -> None:
    """记录不在内存里留状态：换一个对象接着写，序号接着文件里的项往下数。"""
    first = open_at(tmp_path)
    for number in range(10):
        first.append(UserMessage(f"第{number}问"), f"turn-{number}")
    later = Transcript(first.path, "thread-1", now=lambda: WHEN)
    assert later.append(UserMessage("第十一问"), "turn-10").seq == 11
    assert read(first.path)[-1].item == UserMessage("第十一问")


@pytest.mark.parametrize(
    ("broken", "match"),
    [
        (b"{not json", "不是合法的 JSON"),
        (b"[1, 2]", "不是 JSON 对象"),
        (line(seq=0), "信封"),
        (line(seq="1"), "信封"),
        (line(seq=True), "信封"),
        (line(time="昨天"), "时间"),
        (line(thread_id=""), "信封"),
        (line(turn_id=...), "信封"),
        (line(type="mystery"), "看不懂的项类型"),
        (line(type=...), "看不懂的项类型"),
        (line(content=...), "缺少字段 content"),
        (line(content=7), "字段 content 类型不对"),
        (line(extra="x"), "多出字段"),
    ],
)
def test_a_broken_line_is_an_error_not_a_silent_drop(broken: object, match: str) -> None:
    """看不懂的行直接报错：不悄悄丢掉，也不 guess。"""
    raw = broken if isinstance(broken, bytes) else json.dumps(broken).encode()
    with pytest.raises(BrokenItem, match=match):
        decode(raw)


def test_errors_do_not_echo_the_line(tmp_path: Path) -> None:
    """出错说明里不回显那一行的内容：记录里可能有不该到处出现的东西。"""
    with pytest.raises(BrokenItem) as excinfo:
        decode(json.dumps(line(content=7)).encode())
    assert "你好" not in str(excinfo.value)


def test_fields_are_checked_against_their_item_kind() -> None:
    """tool_result 的 error 必须是真值，turn_end 的 outcome 必须是四种结局之一。

    approval 的决定只有批准和拒绝两种。
    """
    result = encode(Entry(1, WHEN, "t", "u", ToolResult("c1", "内容", error=True, summary="摘要")))
    assert decode(json.dumps(result)) == Entry(
        1, WHEN, "t", "u", ToolResult("c1", "内容", True, "摘要")
    )
    end = encode(Entry(1, WHEN, "t", "u", TurnEnd(Outcome.ERROR, "原因")))
    approval = encode(Entry(1, WHEN, "t", "u", Approval("c1", "t", "{}", "approved")))
    for record in (
        {**result, "error": "yes"},
        {**end, "outcome": "finished"},
        {**approval, "decision": "maybe"},
    ):
        with pytest.raises(BrokenItem, match="类型不对"):
            decode(json.dumps(record))


def test_the_envelope_fields_are_fixed() -> None:
    """信封只有四个字段；schema 与数据类的一致性由 tests/unit/test_thread_items_schema.py 守。"""
    assert ENVELOPE == ("seq", "time", "thread_id", "turn_id")
    assert set(encode(Entry(1, WHEN, "t", "u", TurnStart()))) == {*ENVELOPE, "type"}


def test_appending_refuses_to_continue_a_half_line(tmp_path: Path) -> None:
    """文件末尾是半行时不接着写，文件原样不动。"""
    path = tmp_path / "t.jsonl"
    path.write_bytes(json.dumps(line(seq=1)).encode() + b"\n" + b'{"seq": 2, "type": "user_mess')
    transcript = Transcript(path, "thread-1", now=lambda: WHEN)
    with pytest.raises(BrokenItem, match="半行"):
        transcript.append(UserMessage("接不上"), "turn-1")
    assert path.read_bytes().count(b"\n") == 1
