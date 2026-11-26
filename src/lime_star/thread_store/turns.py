"""回合的读模型：一份会话记录里有几个回合，最后一个回合怎样收场，没收场的要补上什么（R9.3、R9.4）。

读模型只看传进来的项，不读文件，也不留状态：显示和恢复都从同一份会话记录派生这里的事实。
有开始、没有结局的回合是中断：进程没有收尾就结束了。读记录的一方把它判为中断，并给出要补进记录的项，
这样每个回合都有结局，每次调用都有且只有一条结果（architecture.md 的 7.2、7.4）。
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass

from lime_star.protocol import (
    Approval,
    Entry,
    Item,
    Outcome,
    ToolCall,
    ToolResult,
    TurnEnd,
    TurnStart,
)
from lime_star.thread_store.transcript import BrokenItem

NOT_CLOSED = "进程没有收尾就结束了"
WAITING = "没有执行：进程在等待批准时被结束。"
UNKNOWN = "结果未知：进程在执行途中被结束，这次操作可能已经发生。"
NO_RESULT = "没有结果：进程在这次调用返回之前被结束。"


@dataclass(frozen=True)
class Interrupted:
    """有开始、没有结局的回合，读记录的一方把它判为中断。

    reason 是给用户看的原因。items 是要追加进记录的项：没有结果的调用各一条结果，最后是中断结局。
    """

    turn_id: str
    reason: str
    items: tuple[Item, ...]


def turn_count(entries: Sequence[Entry]) -> int:
    """一份会话记录里有多少个回合：数回合开始项。"""
    return sum(1 for entry in entries if isinstance(entry.item, TurnStart))


def last_reason(entries: Sequence[Entry]) -> str:
    """最后一个回合没有正常完成时，它的结局项里写的原因；正常完成或没有回合时是空串。

    只看已经写了的结局。没有结局的回合见 interrupted。
    """
    start = _last_start(entries)
    for entry in entries[start:] if start >= 0 else ():
        if isinstance(entry.item, TurnEnd):
            return "" if entry.item.outcome is Outcome.DONE else entry.item.reason
    return ""


def interrupted(entries: Sequence[Entry], approve_first: Collection[str]) -> Interrupted | None:
    """最后一个回合有开始、没有结局时把它判为中断（R9.3）；别的情形返回 None。

    approve_first 是要先经批准才执行的工具的名称。这类工具的调用没有批准项，说明注册表没有放行，
    这次操作没有执行；别的工具没有批准这一步，只能说没有结果。

    记录的中间出现没有结局的回合时抛 BrokenItem：那份记录被改过，或者被两个进程同时写过。
    """
    _check_shape(entries)
    start = _last_start(entries)
    if start < 0 or any(isinstance(entry.item, TurnEnd) for entry in entries[start:]):
        return None
    turn = entries[start:]
    items: list[Item] = []
    waiting: str | None = None
    running: str | None = None
    for entry in turn:
        call = entry.item
        if not isinstance(call, ToolCall) or _result_of(turn, call.call_id) is not None:
            continue
        approval = _approval_of(turn, call.call_id)
        if approval is None and call.name in approve_first:
            text = WAITING
            waiting = waiting if waiting is not None else call.name
        elif approval is not None and approval.decision == "approved":
            text = UNKNOWN
            running = running if running is not None else call.name
        else:
            text = NO_RESULT
        items.append(ToolResult(call.call_id, text, error=True, summary=text))
    if waiting is not None:
        reason = f"{NOT_CLOSED}，当时正在等待批准 {waiting}，这次操作没有执行"
    elif running is not None:
        reason = f"{NOT_CLOSED}，{running} 已获批准却没有留下结果，这次操作可能已经发生"
    else:
        reason = f"{NOT_CLOSED}，当时没有等待批准或执行中的危险操作"
    items.append(TurnEnd(Outcome.INTERRUPTED, reason))
    return Interrupted(turn[0].turn_id, reason, tuple(items))


def _check_shape(entries: Sequence[Entry]) -> None:
    """回合以开始项起头、以结局项收尾；只有最后一个回合可以没有结局。"""
    open_since: int | None = None
    for index, entry in enumerate(entries):
        if isinstance(entry.item, TurnStart):
            if open_since is not None:
                raise BrokenItem("有一个回合没有结局，后面却又开始了一个回合")
            open_since = index
        elif isinstance(entry.item, TurnEnd):
            if open_since is None:
                raise BrokenItem("有回合结局，前面却没有回合开始")
            open_since = None


def _last_start(entries: Sequence[Entry]) -> int:
    """最后一个回合开始项的位置；一个回合都没有时返回 -1。"""
    for index in range(len(entries) - 1, -1, -1):
        if isinstance(entries[index].item, TurnStart):
            return index
    return -1


def _result_of(turn: Sequence[Entry], call_id: str) -> ToolResult | None:
    """这个回合里指向这次调用的结果；没有时返回 None。"""
    for entry in turn:
        if isinstance(entry.item, ToolResult) and entry.item.call_id == call_id:
            return entry.item
    return None


def _approval_of(turn: Sequence[Entry], call_id: str) -> Approval | None:
    """这个回合里指向这次调用的批准项；没有时返回 None。"""
    for entry in turn:
        if isinstance(entry.item, Approval) and entry.item.call_id == call_id:
            return entry.item
    return None
