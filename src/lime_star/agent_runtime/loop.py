"""回合循环：模型请求、执行工具、结果写回会话记录、下一次模型请求，直到模型不再调用工具（R12.1）。

循环是纯核心：不联网，不导入模型客户端、工具实现或存储。外界只通过 protocol 里的三个接口进来
（模型、工具集、会话记录），由 app 回合入口装配。依赖方向有守卫，守卫在
tests/integration/test_guard_architecture.py。

一步一物化：一次模型响应先落成项并写进记录，再执行其中的工具调用；
一次响应里的工具全部执行完、结果都写回之后，才发起下一次请求。

回合以回合开始项开头，以回合结局项收尾（R12.7）。结局有四种：完成、步数上限（R12.3）、
模型出错（R12.4）、用户取消（R12.5）。模型请求失败结束回合，不重试；
工具出错、未知工具、参数不合法都作为工具结果交回模型，回合继续（R12.2）。

没有执行的调用也有一条出错的结果：取消时被中断的调用和它后面的调用，达到步数上限时
最后一次响应里的调用。这样记录里每次调用都有且只有一条结果，发给模型的对话才是完整的。

参考 lime 仓库 lime-rs/crates/agent-runtime/src/reply_loop.rs 的纯状态机做法，以及同目录
provider_turn.rs 文件头写明的一步一物化约定。只取思路，按本仓库语境实现，没有复制原文。
"""

from collections.abc import Sequence

from lime_star.protocol import (
    Entry,
    Item,
    Journal,
    Model,
    ModelFailure,
    ModelReply,
    ModelText,
    Outcome,
    Reasoning,
    ToolCall,
    ToolResult,
    ToolSet,
    TurnEnd,
    TurnResult,
    TurnStart,
    UserMessage,
)

MAX_REQUESTS = 20
"""一个回合最多发起的模型请求次数（R12.3，决策 D-10）。"""

CANCELLED_BY_USER = "用户按 Ctrl+C 取消"
STEP_LIMIT_REACHED = f"已达到步数上限（一个回合最多 {MAX_REQUESTS} 次模型请求）"
NOT_RUN_CANCELLED = "没有执行：用户取消了这个回合。"
NOT_RUN_AT_LIMIT = "没有执行：回合已达到步数上限。"


def run_turn(
    turn_id: str,
    history: Sequence[Entry],
    text: str,
    *,
    model: Model,
    tools: ToolSet,
    journal: Journal,
) -> TurnResult:
    """跑完一个回合并返回它的结局：写下回合开始项，循环到模型不再调用工具，写下回合结局项。

    history 是这个回合之前的全部项，不会被改动。等待模型或执行工具时按 Ctrl+C，回合以取消结束：
    已经写进记录的项留着，后面的工具调用不再执行，各有一条"没有执行"的结果。
    """
    seen: list[Entry] = [*history]

    def write(item: Item) -> None:
        seen.append(journal(item, turn_id))

    def finish(outcome: Outcome, reason: str = "", reply: str = "") -> TurnResult:
        write(TurnEnd(outcome, reason))
        return TurnResult(turn_id, outcome, reason, reply)

    specs = tools.specs()
    write(TurnStart())
    write(UserMessage(text))
    requests = 0
    try:
        while True:
            requests += 1
            answer = model.respond(turn_id, seen, specs)
            if isinstance(answer, ModelFailure):
                return finish(Outcome.ERROR, answer.reason)
            for item in _items_of(answer):
                write(item)
            if not answer.calls:
                return finish(Outcome.DONE, "", answer.text)
            if requests == MAX_REQUESTS:
                # 最后一次响应仍调用工具：一个也不执行（R12.3），每个调用补一条"没有执行"的结果。
                for call in answer.calls:
                    write(_not_run(call, NOT_RUN_AT_LIMIT))
                return finish(Outcome.STEP_LIMIT, STEP_LIMIT_REACHED)
            for index, call in enumerate(answer.calls):
                try:
                    result = tools.execute(call)
                except KeyboardInterrupt:
                    # 被中断的调用没有完成，它后面的调用没有开始。
                    for skipped in answer.calls[index:]:
                        write(_not_run(skipped, NOT_RUN_CANCELLED))
                    raise
                write(result)
    except KeyboardInterrupt:
        return finish(Outcome.CANCELLED, CANCELLED_BY_USER)


def _items_of(answer: ModelReply) -> list[Item]:
    """一次模型响应落成的项，顺序固定：推理、文本、工具调用。"""
    items: list[Item] = []
    if answer.reasoning:
        items.append(Reasoning(answer.reasoning))
    if answer.text:
        items.append(ModelText(answer.text))
    items.extend(answer.calls)
    return items


def _not_run(call: ToolCall, reason: str) -> ToolResult:
    return ToolResult(call.call_id, reason, error=True, summary=reason)
