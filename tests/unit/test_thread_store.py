"""会话的查找、独占写入和回合读模型的单元测试（R9.1-S1、R9.3、R9.5）。

证据等级：Unit。不联网，不启动进程，只凭临时目录里的文件和手写的项。
经 app 回合入口的恢复在 tests/integration/test_resume.py 里，真实进程里的 --resume 在
tests/integration/test_cli_resume.py 里。
"""

import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from lime_star.protocol import (
    Approval,
    Entry,
    Item,
    Outcome,
    ToolCall,
    ToolResult,
    TurnEnd,
    TurnStart,
    UserMessage,
)
from lime_star.thread_store import (
    BrokenItem,
    Busy,
    Hold,
    Transcript,
    interrupted,
    last_reason,
    latest,
    turn_count,
)
from lime_star.thread_store.turns import NO_RESULT, NOT_CLOSED, UNKNOWN, WAITING

T0 = datetime(2026, 11, 26, 1, 0, 0, tzinfo=UTC)
DANGEROUS = frozenset({"write_file", "run_command"})
WRITE = ToolCall(call_id="c1", name="write_file", arguments='{"path": "a.txt"}')
READ = ToolCall(call_id="c2", name="read_file", arguments="{}")
NOTHING_PENDING = f"{NOT_CLOSED}，当时没有等待批准或执行中的危险操作"


def clock(minutes: float) -> Callable[[], datetime]:
    """一个总给出固定时间的时钟。"""
    return lambda: T0 + timedelta(minutes=minutes)


def thread(base: Path, thread_id: str, *messages: str, minutes: float = 0) -> Transcript:
    """在工作目录下写一份只有用户消息的会话记录，每一项的时间都相同。"""
    record = Transcript.at(base, thread_id, now=clock(minutes))
    for number, message in enumerate(messages):
        record.append(UserMessage(message), f"turn-{number}")
    return record


def entry(number: int, item: Item, turn: str = "t") -> Entry:
    return Entry(number, T0, "thread-1", turn, item)


def open_turn(*items: Item, turn: str = "cut") -> tuple[Entry, ...]:
    """前面是一个已经完成的回合，最后是一个有开始、没有结局的回合；items 是它开始之后的项。"""
    return (
        entry(1, TurnStart(), "done"),
        entry(2, UserMessage("旧问题"), "done"),
        entry(3, TurnEnd(Outcome.DONE, ""), "done"),
        entry(4, TurnStart(), turn),
        *(entry(number + 5, item, turn) for number, item in enumerate(items)),
    )


def ending(reason: str) -> TurnEnd:
    return TurnEnd(Outcome.INTERRUPTED, reason)


def test_the_latest_session_is_the_one_whose_last_item_is_newest(tmp_path: Path) -> None:
    """R9.1-S1：恢复最后有活动的那个会话。活动以记录里最后一项的时间为准，不看文件的修改时间。"""
    first = thread(tmp_path, "first", "甲", minutes=0)
    second = thread(tmp_path, "second", "乙", minutes=3)
    Transcript(first.path, "first", now=clock(5)).append(UserMessage("又一句"), "turn-9")
    later = (T0 + timedelta(days=1)).timestamp()
    os.utime(second.path, (later, later))  # second 的文件修改时间更晚，不算活动
    assert latest(tmp_path) == "first"


def test_the_latest_of_two_sessions_is_the_later_one(tmp_path: Path) -> None:
    thread(tmp_path, "older", "甲", minutes=0)
    thread(tmp_path, "newer", "乙", minutes=3)
    assert latest(tmp_path) == "newer"


def test_without_any_session_there_is_nothing_to_resume(tmp_path: Path) -> None:
    """工作目录下没有会话目录、或者目录是空的：没有可恢复的会话。"""
    assert latest(tmp_path) is None
    Transcript.at(tmp_path, "nothing")  # 建好了 .lime-star/threads，还没写下一项
    assert latest(tmp_path) is None


def test_a_record_without_a_complete_item_is_not_activity(tmp_path: Path) -> None:
    """一项都没写下的空文件、只剩半行的文件，都不算有活动；它们不挡住另一个会话被恢复。"""
    empty = thread(tmp_path, "empty").path
    empty.write_bytes(b"")
    half = thread(tmp_path, "half").path
    half.write_bytes('{"seq": 1, "content": "半'.encode()[:-1])
    thread(tmp_path, "whole", "甲", minutes=0)
    assert (latest(tmp_path), empty.exists(), half.exists()) == ("whole", True, True)


def test_a_last_item_that_cannot_be_read_is_an_error(tmp_path: Path) -> None:
    """最后一项读不懂时不悄悄跳过它去恢复另一个会话。"""
    whole = thread(tmp_path, "whole", "甲", minutes=0)
    broken = thread(tmp_path, "broken", "乙", minutes=3)
    broken.path.write_bytes(
        b'{"seq": 1, "time": "2026-11-26T01:03:00+00:00", "thread_id": "broken", '
        b'"turn_id": "t", "type": "mystery"}\n'
    )
    with pytest.raises(BrokenItem, match="看不懂的项类型"):
        latest(tmp_path)
    assert whole.path.exists()


def test_a_hold_is_exclusive_and_released(tmp_path: Path) -> None:
    """一个会话同一时刻只有一个写入者：取过之后，同一个进程里的再次获取也被拒；放开之后可以再取。"""
    first = Hold.take(tmp_path, "t1")
    assert (tmp_path / ".lime-star" / "locks" / "t1.lock").is_file()
    with pytest.raises(Busy):
        Hold.take(tmp_path, "t1")
    Hold.take(tmp_path, "t2").release()  # 别的会话不受影响
    first.release()
    again = Hold.take(tmp_path, "t1")
    again.release()
    again.release()  # 重复放开什么都不做
    Hold.take(tmp_path, "t1").release()


def test_the_lock_directory_is_created_on_demand(tmp_path: Path) -> None:
    """取独占写入时才建 .lime-star/locks。"""
    assert list(tmp_path.iterdir()) == []
    Hold.take(tmp_path, "t1").release()
    assert [path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*")] == [
        ".lime-star",
        ".lime-star/locks",
        ".lime-star/locks/t1.lock",
    ]


def test_closed_turns_are_not_interrupted() -> None:
    """每个回合都有结局时没有要补的项；数的是回合开始项；原因取最后一个回合的结局。"""
    entries = (
        entry(1, TurnStart()),
        entry(2, UserMessage("问")),
        entry(3, TurnEnd(Outcome.DONE, "")),
        entry(4, TurnStart(), "next"),
        entry(5, TurnEnd(Outcome.CANCELLED, "用户按 Ctrl+C 取消"), "next"),
    )
    assert interrupted(entries, DANGEROUS) is None
    assert (turn_count(entries), last_reason(entries)) == (2, "用户按 Ctrl+C 取消")


@pytest.mark.parametrize(
    "outcome", [Outcome.DONE, Outcome.ERROR, Outcome.CANCELLED, Outcome.STEP_LIMIT]
)
def test_only_an_unfinished_last_turn_counts_as_interrupted(outcome: Outcome) -> None:
    """最后一个回合有结局就不算中断；原因只在它没有正常完成时才给。"""
    entries = (entry(1, TurnStart()), entry(2, UserMessage("问")), entry(3, TurnEnd(outcome, "r")))
    assert interrupted(entries, DANGEROUS) is None
    assert last_reason(entries) == ("" if outcome is Outcome.DONE else "r")


def test_nothing_is_interrupted_in_an_empty_record() -> None:
    assert (interrupted((), DANGEROUS), turn_count(()), last_reason(())) == (None, 0, "")


def test_a_turn_cut_off_with_no_dangerous_operation_pending_only_gets_its_ending() -> None:
    """有开始、没有结局，当时没有等待批准或执行中的危险操作：只补一条中断结局，原因写明这一点。"""
    for items in ((), (READ, ToolResult("c2", "内容"))):
        cut = interrupted(open_turn(UserMessage("问"), *items), DANGEROUS)
        assert cut is not None
        assert (cut.turn_id, cut.items, cut.reason) == (
            "cut",
            (ending(NOTHING_PENDING),),
            NOTHING_PENDING,
        )


def test_a_read_only_call_cut_off_gets_no_result_and_no_blame() -> None:
    """只读的调用没有结果：补一条"没有结果"；原因仍然是没有危险操作悬着。"""
    cut = interrupted(open_turn(UserMessage("问"), READ), DANGEROUS)
    assert cut is not None
    assert cut.items == (ToolResult("c2", NO_RESULT, True, NO_RESULT), ending(NOTHING_PENDING))


def test_a_dangerous_call_waiting_for_approval_was_not_executed() -> None:
    """R9.3-S2：危险工具的调用没有批准项，说明注册表没有放行，这次操作没有执行。"""
    entries = open_turn(UserMessage("写 a.txt"), WRITE)
    cut = interrupted(entries, DANGEROUS)
    assert cut is not None
    assert cut.items == (
        ToolResult("c1", WAITING, True, WAITING),
        ending(f"{NOT_CLOSED}，当时正在等待批准 write_file，这次操作没有执行"),
    )
    assert cut.reason == f"{NOT_CLOSED}，当时正在等待批准 write_file，这次操作没有执行"


def test_an_approved_call_without_a_result_may_have_run() -> None:
    """危险工具的调用有批准项、没有结果：操作可能已经发生，原因和结果都如实说不知道。"""
    approved = Approval("c1", "write_file", WRITE.arguments, "approved")
    cut = interrupted(open_turn(UserMessage("写 a.txt"), WRITE, approved), DANGEROUS)
    assert cut is not None
    assert cut.items == (
        ToolResult("c1", UNKNOWN, True, UNKNOWN),
        ending(f"{NOT_CLOSED}，write_file 已获批准却没有留下结果，这次操作可能已经发生"),
    )


def test_a_rejected_call_and_a_call_that_needs_no_approval_only_lack_a_result() -> None:
    """批准项写的是拒绝，或者工具本来不需要批准：只能说没有结果，不能说没有执行，也不能说可能执行了。"""
    rejected = Approval("c1", "write_file", WRITE.arguments, "rejected")
    for items in ((WRITE, rejected), (READ,)):
        cut = interrupted(open_turn(UserMessage("问"), *items), DANGEROUS)
        assert cut is not None
        [call] = [item for item in items if isinstance(item, ToolCall)]
        assert cut.items == (
            ToolResult(call.call_id, NO_RESULT, True, NO_RESULT),
            ending(NOTHING_PENDING),
        )


def test_only_the_calls_without_results_get_one() -> None:
    """一次响应里的两个调用，第一个有结果、第二个没有：只给第二个补结果，原因指向它。"""
    second = ToolCall(call_id="c9", name="run_command", arguments='{"command": "dir"}')
    entries = open_turn(
        UserMessage("问"),
        READ,
        second,
        ToolResult("c2", "内容", summary="读到 1 行"),
    )
    cut = interrupted(entries, DANGEROUS)
    assert cut is not None
    assert cut.items == (
        ToolResult("c9", WAITING, True, WAITING),
        ending(f"{NOT_CLOSED}，当时正在等待批准 run_command，这次操作没有执行"),
    )


def test_a_turn_left_open_in_the_middle_is_a_broken_record() -> None:
    """记录的中间出现有开始、没有结局的回合：它被改过，或者被两个进程同时写过。"""
    entries = (
        entry(1, TurnStart()),
        entry(2, UserMessage("问")),
        entry(3, TurnStart(), "next"),
        entry(4, TurnEnd(Outcome.DONE, ""), "next"),
    )
    with pytest.raises(BrokenItem, match="没有结局"):
        interrupted(entries, DANGEROUS)


def test_an_ending_without_a_start_is_a_broken_record() -> None:
    with pytest.raises(BrokenItem, match="回合开始"):
        interrupted((entry(1, TurnEnd(Outcome.DONE, "")),), DANGEROUS)


def test_the_reason_of_an_unfinished_turn_is_read_from_what_is_written() -> None:
    """last_reason 只看已经写了的结局；没有结局的回合原因由 interrupted 给。"""
    entries = open_turn(UserMessage("问"))
    assert (last_reason(entries), turn_count(entries)) == ("", 2)
