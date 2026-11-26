"""回合循环的单元测试：不联网，模型、工具和会话记录都是脚本（R12.1 到 R12.5、R12.7）。

证据等级：Unit。这里守的是循环这个纯模块的状态转移，以及它写进记录的项。
它和模型边界、注册表、会话记录文件的接线在 tests/integration 里从 app 回合入口验证。
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from lime_star.agent_runtime.loop import (
    CANCELLED_BY_USER,
    NOT_RUN_AT_LIMIT,
    NOT_RUN_CANCELLED,
    STEP_LIMIT_REACHED,
    run_turn,
)
from lime_star.protocol import (
    Entry,
    Halted,
    Item,
    Json,
    ModelFailure,
    ModelReply,
    ModelResult,
    ModelText,
    Outcome,
    ToolCall,
    ToolResult,
    ToolSpec,
    TurnEnd,
    TurnResult,
    TurnStart,
    UserMessage,
)

TEXT = "读一下文件"
TURN = "turn-1"
THREAD = "thread-1"
WHEN = datetime(2026, 11, 25, tzinfo=UTC)


class ScriptedModel:
    """按脚本回应的模型：每一步是一次响应，或者一个要抛出的异常。记下每次请求收到的东西。"""

    def __init__(self, *steps: ModelResult | BaseException) -> None:
        self.steps: list[ModelResult | BaseException] = list(steps)
        self.histories: list[tuple[Entry, ...]] = []
        self.offered: list[tuple[ToolSpec, ...]] = []
        self.turn_ids: list[str] = []

    def respond(
        self,
        turn_id: str,
        history: Sequence[Entry],
        tools: Sequence[ToolSpec],
    ) -> ModelResult:
        self.turn_ids.append(turn_id)
        self.histories.append(tuple(history))
        self.offered.append(tuple(tools))
        step = self.steps.pop(0)
        if isinstance(step, BaseException):
            raise step
        return step


@dataclass(frozen=True)
class Spec:
    """脚本工具向外的说明。"""

    name: str

    @property
    def description(self) -> str:
        return "脚本工具"

    @property
    def parameters(self) -> dict[str, Json]:
        return {"type": "object"}


class FakeTools:
    """按脚本回应的工具集：登记几个工具，按名称给出结果或要抛出的异常，也可以在执行时回调。"""

    def __init__(
        self,
        *names: str,
        results: dict[str, ToolResult | BaseException] | None = None,
        on_execute: Callable[[ToolCall], None] | None = None,
    ) -> None:
        self.names = names
        self.results = results or {}
        self.on_execute = on_execute
        self.executed: list[ToolCall] = []

    def specs(self) -> tuple[ToolSpec, ...]:
        return tuple(Spec(name) for name in self.names)

    def execute(self, call: ToolCall) -> ToolResult:
        self.executed.append(call)
        if self.on_execute is not None:
            self.on_execute(call)
        step = self.results.get(call.name)
        if isinstance(step, BaseException):
            raise step
        if step is None:
            return ToolResult(call.call_id, f"{call.name} 的结果")
        return step


class Recorder:
    """会话记录的脚本替身：记下写入的项，按写入顺序配上信封。"""

    def __init__(self) -> None:
        self.entries: list[Entry] = []
        self.turn_ids: list[str] = []

    def append(self, item: Item, turn_id: str) -> Entry:
        self.turn_ids.append(turn_id)
        entry = Entry(len(self.entries) + 1, WHEN, THREAD, turn_id, item)
        self.entries.append(entry)
        return entry


def entry(seq: int, item: Item) -> Entry:
    return Entry(seq, WHEN, THREAD, TURN, item)


def call(name: str, call_id: str) -> ToolCall:
    return ToolCall(call_id=call_id, name=name, arguments="{}")


def result_of(call_: ToolCall) -> ToolResult:
    return ToolResult(call_.call_id, f"{call_.name} 的结果")


def items(record: Recorder) -> list[Item]:
    return [entry.item for entry in record.entries]


def kinds(written: Sequence[Item]) -> list[str]:
    return [type(item).__name__ for item in written]


def run(
    model: ScriptedModel, tools: FakeTools, history: Sequence[Entry] = ()
) -> tuple[TurnResult, Recorder]:
    """跑一个回合，返回它的结局和写入的项。"""
    record = Recorder()
    result = run_turn(TURN, history, TEXT, model=model, tools=tools, journal=record.append)
    return result, record


def assert_paired(record: Recorder) -> None:
    """记录里每次工具调用都有且只有一条结果，结果排在调用后面。"""
    positions = [(index, item) for index, item in enumerate(items(record))]
    calls = sorted(index for index, item in positions if isinstance(item, ToolCall))
    results = sorted(index for index, item in positions if isinstance(item, ToolResult))
    assert len(calls) == len(results)
    assert all(call_at < result_at for call_at, result_at in zip(calls, results, strict=True))
    written = items(record)
    assert sorted(item.call_id for item in written if isinstance(item, ToolResult)) == sorted(
        item.call_id for item in written if isinstance(item, ToolCall)
    )


def test_a_reply_without_tool_calls_ends_the_turn() -> None:
    """R12.1、R12.7：模型的回复不再调用工具，回合完成；记录以回合开始开头、以完成结局收尾。"""
    model = ScriptedModel(ModelReply(text="完成了"))
    result, record = run(model, FakeTools())
    assert (result.outcome, result.reply, result.reason) == (Outcome.DONE, "完成了", "")
    assert (result.turn_id, model.turn_ids) == (TURN, [TURN])
    assert record.entries == [
        entry(1, TurnStart()),
        entry(2, UserMessage(TEXT)),
        entry(3, ModelText("完成了")),
        entry(4, TurnEnd(Outcome.DONE, "")),
    ]
    assert record.turn_ids == [TURN] * 4


def test_a_tool_call_is_run_then_the_loop_goes_on() -> None:
    """R12.1-S1（继续）：第一次回复调用工具，结果写回记录后才发第二次请求，第二次回复是最终回复。"""
    first_call = call("read_file", "c1")
    model = ScriptedModel(ModelReply(calls=(first_call,)), ModelReply(text="读到了"))
    tools = FakeTools("read_file")
    result, record = run(model, tools)
    assert (result.outcome, result.reply) == (Outcome.DONE, "读到了")
    assert tools.executed == [first_call]
    assert kinds(items(record)) == [
        "TurnStart",
        "UserMessage",
        "ToolCall",
        "ToolResult",
        "ModelText",
        "TurnEnd",
    ]
    assert record.entries[-1].item == TurnEnd(Outcome.DONE, "")
    first, second = model.histories
    assert first == (entry(1, TurnStart()), entry(2, UserMessage(TEXT)))
    assert second[:2] == first
    assert second[2].item == first_call
    assert second[3].item == result_of(first_call)
    assert_paired(record)


def test_every_tool_result_is_recorded_before_the_next_request() -> None:
    """R12.1-S2：一次请求了三次工具调用，按顺序执行，三个结果都在第二次请求的历史里。"""
    calls = tuple(call(f"tool{n}", f"c{n}") for n in (1, 2, 3))
    model = ScriptedModel(ModelReply(calls=calls), ModelReply(text="都做完了"))
    tools = FakeTools("tool1", "tool2", "tool3")
    result, record = run(model, tools)
    assert (result.outcome, result.reply) == (Outcome.DONE, "都做完了")
    assert tools.executed == list(calls)
    assert kinds(items(record)) == [
        "TurnStart",
        "UserMessage",
        "ToolCall",
        "ToolCall",
        "ToolCall",
        "ToolResult",
        "ToolResult",
        "ToolResult",
        "ModelText",
        "TurnEnd",
    ]
    second = model.histories[1]
    assert [seen.item for seen in second[2:5]] == list(calls)
    assert [seen.item for seen in second[5:8]] == [result_of(made) for made in calls]
    assert_paired(record)


def test_the_response_is_recorded_before_its_tools_run() -> None:
    """一步一物化（R6.2）：工具开始执行时，这次响应的项已经在记录里。"""
    seen_at_run: list[list[str]] = []
    tools = FakeTools(
        "tool1",
        "tool2",
        on_execute=lambda _call: seen_at_run.append(kinds(items(record))),
    )
    calls = (call("tool1", "c1"), call("tool2", "c2"))
    model = ScriptedModel(ModelReply(text="我先看看", calls=calls), ModelReply(text="好了"))
    record = Recorder()
    run_turn(TURN, (), TEXT, model=model, tools=tools, journal=record.append)
    assert seen_at_run == [
        ["TurnStart", "UserMessage", "ModelText", "ToolCall", "ToolCall"],
        ["TurnStart", "UserMessage", "ModelText", "ToolCall", "ToolCall", "ToolResult"],
    ]


def test_a_failed_tool_result_does_not_end_the_turn() -> None:
    """R12.2：工具出错是工具结果，照样交给模型；结束的是这次调用，不是这一回合。"""
    missing = ToolResult("c1", "文件不存在：x.txt。", error=True)
    tools = FakeTools("read_file", results={"read_file": missing})
    model = ScriptedModel(
        ModelReply(calls=(call("read_file", "c1"),)), ModelReply(text="没有这个文件")
    )
    result, record = run(model, tools)
    assert (result.outcome, result.reply) == (Outcome.DONE, "没有这个文件")
    assert items(record)[3] == missing
    assert model.histories[1][-1].item == missing
    assert_paired(record)


def test_the_step_limit_ends_the_turn_without_running_the_last_tools() -> None:
    """R12.3-S1、R12.7：模型每次都调用工具，第 20 次请求结束后回合以步数上限结束。"""
    model = ScriptedModel(*(ModelReply(calls=(call("read_file", f"c{n}"),)) for n in range(1, 21)))
    tools = FakeTools("read_file")
    result, record = run(model, tools)
    assert result.outcome is Outcome.STEP_LIMIT
    assert (result.reason, result.reply) == (STEP_LIMIT_REACHED, "")
    assert (len(model.histories), len(tools.executed), model.steps) == (20, 19, [])
    written = items(record)
    assert kinds(written) == [
        "TurnStart",
        "UserMessage",
        *(["ToolCall", "ToolResult"] * 20),
        "TurnEnd",
    ]
    # 第 20 次响应的调用留在记录里，没有执行，补了一条"没有执行"的结果。
    assert written[-3:] == [
        call("read_file", "c20"),
        ToolResult("c20", NOT_RUN_AT_LIMIT, True, NOT_RUN_AT_LIMIT),
        TurnEnd(Outcome.STEP_LIMIT, STEP_LIMIT_REACHED),
    ]
    assert_paired(record)


def test_a_model_failure_ends_the_turn_and_is_not_retried() -> None:
    """R12.4、R12.7：模型请求失败，回合以出错结束，原因写进结局项，不再发起请求（决策 D-11）。"""
    model = ScriptedModel(
        ModelReply(calls=(call("read_file", "c1"),)),
        ModelFailure("鉴权失败（HTTP 401）"),
        ModelReply(text="不该被用到"),
    )
    result, record = run(model, FakeTools("read_file"))
    assert (result.outcome, result.reason, result.reply) == (
        Outcome.ERROR,
        "鉴权失败（HTTP 401）",
        "",
    )
    assert len(model.histories) == 2
    assert kinds(items(record)) == ["TurnStart", "UserMessage", "ToolCall", "ToolResult", "TurnEnd"]
    assert items(record)[-1] == TurnEnd(Outcome.ERROR, "鉴权失败（HTTP 401）")
    assert_paired(record)


def test_ctrl_c_while_waiting_for_the_model_cancels_the_turn() -> None:
    """R12.5-S2、R12.7：等待模型时按 Ctrl+C，不再发起任何请求，结局项写明取消。"""
    model = ScriptedModel(
        ModelReply(calls=(call("read_file", "c1"),)),
        KeyboardInterrupt(),
        ModelReply(text="不该被用到"),
    )
    result, record = run(model, FakeTools("read_file"))
    assert (result.outcome, result.reason, result.reply) == (
        Outcome.CANCELLED,
        CANCELLED_BY_USER,
        "",
    )
    assert len(model.histories) == 2
    assert items(record)[-1] == TurnEnd(Outcome.CANCELLED, CANCELLED_BY_USER)
    assert_paired(record)


def test_ctrl_c_during_a_tool_gives_the_remaining_calls_a_result() -> None:
    """R12.5：工具执行中被取消，后面的工具调用不再执行；没有执行的调用各有一条"没有执行"的结果。"""
    calls = tuple(call(f"tool{n}", f"c{n}") for n in (1, 2, 3))
    tools = FakeTools("tool1", "tool2", "tool3", results={"tool2": KeyboardInterrupt()})
    model = ScriptedModel(ModelReply(calls=calls), ModelReply(text="不该被用到"))
    result, record = run(model, tools)
    assert (result.outcome, result.reason) == (Outcome.CANCELLED, CANCELLED_BY_USER)
    assert [made.name for made in tools.executed] == ["tool1", "tool2"]
    assert items(record)[2:] == [
        *calls,
        result_of(calls[0]),
        ToolResult("c2", NOT_RUN_CANCELLED, True, NOT_RUN_CANCELLED),
        ToolResult("c3", NOT_RUN_CANCELLED, True, NOT_RUN_CANCELLED),
        TurnEnd(Outcome.CANCELLED, CANCELLED_BY_USER),
    ]
    assert len(model.histories) == 1
    assert_paired(record)


def test_a_tool_interrupted_midway_keeps_the_result_it_brings_back() -> None:
    """R12.5-S1：工具执行到一半被 Ctrl+C 打断，它带回的结果如实记下，不说成"没有执行"；
    后面的调用没有执行。"""
    calls = tuple(call(f"tool{n}", f"c{n}") for n in (1, 2, 3))
    halted = Halted("命令已被终止。\n已经有一半的输出", summary="已取消，命令已终止")
    tools = FakeTools("tool1", "tool2", "tool3", results={"tool2": halted})
    model = ScriptedModel(ModelReply(calls=calls), ModelReply(text="不该被用到"))
    result, record = run(model, tools)
    assert (result.outcome, result.reason) == (Outcome.CANCELLED, CANCELLED_BY_USER)
    assert [made.name for made in tools.executed] == ["tool1", "tool2"]
    assert items(record)[2:] == [
        *calls,
        result_of(calls[0]),
        ToolResult("c2", "命令已被终止。\n已经有一半的输出", True, "已取消，命令已终止"),
        ToolResult("c3", NOT_RUN_CANCELLED, True, NOT_RUN_CANCELLED),
        TurnEnd(Outcome.CANCELLED, CANCELLED_BY_USER),
    ]
    assert len(model.histories) == 1
    assert_paired(record)


def test_an_interrupted_tool_without_a_summary_shows_its_first_line() -> None:
    """被打断的工具没有给摘要时，终端上的摘要取它带回内容的第一行。"""
    calls = (call("tool1", "c1"), call("tool2", "c2"))
    tools = FakeTools("tool1", "tool2", results={"tool1": Halted("第一行\n第二行")})
    model = ScriptedModel(ModelReply(calls=calls), ModelReply(text="不该被用到"))
    result, record = run(model, tools)
    assert result.outcome is Outcome.CANCELLED
    assert items(record)[4:7] == [
        ToolResult("c1", "第一行\n第二行", True, "第一行"),
        ToolResult("c2", NOT_RUN_CANCELLED, True, NOT_RUN_CANCELLED),
        TurnEnd(Outcome.CANCELLED, CANCELLED_BY_USER),
    ]


def test_the_tools_are_offered_to_every_request() -> None:
    model = ScriptedModel(ModelReply(calls=(call("read_file", "c1"),)), ModelReply(text="好"))
    tools = FakeTools("read_file", "list_dir")
    run(model, tools)
    assert [[spec.name for spec in offered] for offered in model.offered] == [
        ["read_file", "list_dir"],
        ["read_file", "list_dir"],
    ]


def test_reasoning_and_text_are_recorded_before_the_tool_calls() -> None:
    model = ScriptedModel(
        ModelReply(text="我看看", reasoning="想一想", calls=(call("read_file", "c1"),)),
        ModelReply(text="好"),
    )
    result, record = run(model, FakeTools("read_file"))
    assert result.outcome is Outcome.DONE
    assert kinds(items(record)) == [
        "TurnStart",
        "UserMessage",
        "Reasoning",
        "ModelText",
        "ToolCall",
        "ToolResult",
        "ModelText",
        "TurnEnd",
    ]


def test_prior_history_is_sent_first_and_not_recorded_again() -> None:
    """R2.1：之前的项按原顺序排在最前面随请求发出；记录里只有这个回合新写的项。"""
    history = (entry(7, UserMessage("上一问")), entry(8, ModelText("上一答")))
    model = ScriptedModel(ModelReply(text="好"))
    result, record = run(model, FakeTools(), history)
    assert result.outcome is Outcome.DONE
    assert model.histories == [(*history, entry(1, TurnStart()), entry(2, UserMessage(TEXT)))]
    assert items(record) == [
        TurnStart(),
        UserMessage(TEXT),
        ModelText("好"),
        TurnEnd(Outcome.DONE, ""),
    ]
