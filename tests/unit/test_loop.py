"""回合循环的单元测试：不联网，模型和工具都是脚本（R12.1 到 R12.5）。

证据等级：Unit。这里守的是循环这个纯模块的状态转移。它和模型边界、注册表的接线在
tests/integration/test_turn.py 里从 app 回合入口验证。
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from lime_star.agent_runtime.loop import (
    CANCELLED_BY_USER,
    MAX_REQUESTS,
    STEP_LIMIT_REACHED,
    run_turn,
)
from lime_star.protocol import (
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
    TurnResult,
    UserMessage,
)

TEXT = "读一下文件"
TURN = "turn-1"


class ScriptedModel:
    """按脚本回应的模型：每一步是一次响应，或者一个要抛出的异常。记下每次请求收到的东西。"""

    def __init__(self, *steps: ModelResult | BaseException) -> None:
        self.steps: list[ModelResult | BaseException] = list(steps)
        self.histories: list[tuple[Item, ...]] = []
        self.offered: list[tuple[ToolSpec, ...]] = []
        self.turn_ids: list[str] = []

    def respond(
        self, turn_id: str, history: Sequence[Item], tools: Sequence[ToolSpec]
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


def call(name: str, call_id: str) -> ToolCall:
    return ToolCall(call_id=call_id, name=name, arguments="{}")


def kinds(items: Sequence[Item]) -> list[str]:
    return [type(item).__name__ for item in items]


def run(
    model: ScriptedModel, tools: FakeTools, history: Sequence[Item] = ()
) -> tuple[TurnResult, list[Item]]:
    """跑一个回合，返回它的结局和会话记录。"""
    record: list[Item] = []
    result = run_turn(TURN, history, TEXT, model=model, tools=tools, transcript=record)
    return result, record


def test_a_reply_without_tool_calls_ends_the_turn() -> None:
    """R12.1：模型的回复不再调用工具，回合完成；用户消息和回复都在记录里。"""
    model = ScriptedModel(ModelReply(text="完成了"))
    result, record = run(model, FakeTools())
    assert (result.outcome, result.reply, result.reason) == (Outcome.DONE, "完成了", "")
    assert (result.turn_id, model.turn_ids) == (TURN, [TURN])
    assert record == [UserMessage(TEXT), ModelText("完成了")]


def test_a_tool_call_is_run_then_the_loop_goes_on() -> None:
    """R12.1-S1（继续）：第一次回复调用工具，结果写回记录后才发第二次请求，第二次回复是最终回复。"""
    model = ScriptedModel(ModelReply(calls=(call("read_file", "c1"),)), ModelReply(text="读到了"))
    tools = FakeTools("read_file")
    result, record = run(model, tools)
    assert (result.outcome, result.reply) == (Outcome.DONE, "读到了")
    assert [(c.name, c.call_id) for c in tools.executed] == [("read_file", "c1")]
    assert kinds(record) == ["UserMessage", "ToolCall", "ToolResult", "ModelText"]
    first, second = model.histories
    assert first == (UserMessage(TEXT),)
    assert second == (UserMessage(TEXT), record[1], record[2])


def test_every_tool_result_is_recorded_before_the_next_request() -> None:
    """R12.1-S2：一次请求了三次工具调用，按顺序执行，三个结果都在第二次请求的历史里。"""
    calls = tuple(call(f"tool{n}", f"c{n}") for n in (1, 2, 3))
    model = ScriptedModel(ModelReply(calls=calls), ModelReply(text="都做完了"))
    tools = FakeTools("tool1", "tool2", "tool3")
    result, record = run(model, tools)
    assert result.outcome is Outcome.DONE
    assert [c.name for c in tools.executed] == ["tool1", "tool2", "tool3"]
    assert kinds(record) == [
        "UserMessage",
        "ToolCall",
        "ToolCall",
        "ToolCall",
        "ToolResult",
        "ToolResult",
        "ToolResult",
        "ModelText",
    ]
    first, second = model.histories
    assert second[:4] == (*first, *calls)
    assert second[4:7] == tuple(record[4:7])


def test_the_response_is_recorded_before_its_tools_run() -> None:
    """一步一物化（R12.1 的顺序）：工具开始执行时，这次响应的项已经在记录里。"""
    seen_at_run: list[list[str]] = []
    tools = FakeTools(
        "tool1",
        "tool2",
        on_execute=lambda _call: seen_at_run.append(kinds(record)),
    )
    calls = (call("tool1", "c1"), call("tool2", "c2"))
    model = ScriptedModel(ModelReply(text="我先看看", calls=calls), ModelReply(text="好了"))
    record: list[Item] = []
    run_turn(TURN, (), TEXT, model=model, tools=tools, transcript=record)
    assert seen_at_run == [
        ["UserMessage", "ModelText", "ToolCall", "ToolCall"],
        ["UserMessage", "ModelText", "ToolCall", "ToolCall", "ToolResult"],
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
    assert record[2] == missing
    assert model.histories[1][-1] == missing


def test_the_step_limit_ends_the_turn_without_running_tools() -> None:
    """R12.3-S1：模型每次都调用工具，第 20 次请求结束后回合以步数上限结束，之后一个工具也不执行。"""
    calling = ModelReply(calls=(call("read_file", "c20"),))
    model = ScriptedModel(*([calling] * MAX_REQUESTS))
    tools = FakeTools("read_file")
    result, record = run(model, tools)
    assert result.outcome is Outcome.STEP_LIMIT
    assert (result.reason, result.reply) == (STEP_LIMIT_REACHED, "")
    assert "20" in result.reason
    assert len(model.histories) == 20
    assert len(tools.executed) == 19
    assert model.steps == []
    # 第 20 次响应留在记录里，它的工具调用没有结果。
    assert kinds(record) == ["UserMessage"] + ["ToolCall", "ToolResult"] * 19 + ["ToolCall"]


def test_a_model_failure_ends_the_turn_and_is_not_retried() -> None:
    """R12.4：模型请求失败，回合以出错结束，原因原样带回，不再发起请求（决策 D-11）。"""
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
    assert kinds(record) == ["UserMessage", "ToolCall", "ToolResult"]


def test_ctrl_c_while_waiting_for_the_model_cancels_the_turn() -> None:
    """R12.5-S2：等待模型时按 Ctrl+C，不再发起任何请求，回合以取消结束。"""
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
    assert kinds(record) == ["UserMessage", "ToolCall", "ToolResult"]


def test_ctrl_c_during_a_tool_skips_the_tools_after_it() -> None:
    """R12.5：工具执行中被取消，后面的工具调用不再执行，也不补写结果。"""
    calls = tuple(call(f"tool{n}", f"c{n}") for n in (1, 2, 3))
    tools = FakeTools("tool1", "tool2", "tool3", results={"tool2": KeyboardInterrupt()})
    model = ScriptedModel(ModelReply(calls=calls), ModelReply(text="不该被用到"))
    result, record = run(model, tools)
    assert result.outcome is Outcome.CANCELLED
    assert [c.name for c in tools.executed] == ["tool1", "tool2"]
    assert kinds(record) == ["UserMessage", "ToolCall", "ToolCall", "ToolCall", "ToolResult"]
    assert len(model.histories) == 1


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
    assert kinds(record) == [
        "UserMessage",
        "Reasoning",
        "ModelText",
        "ToolCall",
        "ToolResult",
        "ModelText",
    ]


def test_prior_history_is_sent_and_not_recorded_again() -> None:
    """R2.1：之前的项按原顺序随请求发出；记录里只有这个回合新写的项。"""
    history = (UserMessage("上一问"), ModelText("上一答"))
    model = ScriptedModel(ModelReply(text="好"))
    result, record = run(model, FakeTools(), history)
    assert result.outcome is Outcome.DONE
    assert model.histories == [(*history, UserMessage(TEXT))]
    assert record == [UserMessage(TEXT), ModelText("好")]
