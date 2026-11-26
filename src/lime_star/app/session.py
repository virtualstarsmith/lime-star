"""回合入口：建立会话、提交回合、读取会话记录、回应审批。

这里把循环、模型边界、工具边界和会话记录装配起来，回合本身由 agent_runtime 的循环跑完。
会话记录由 thread_store 持有：它是会话的唯一事实源，这里不在内存里留第二份。

危险操作要等用户批准（R7.6）。每个回合有一个等待批准的位置：工具边界请求批准时，这里经提问回调
请 CLI 向用户提问，再用 respond_action 收回决定，先把批准项写进会话记录（R7.12），再把决定交给
工具边界。等待中的批准只在内存里：进程在等待时被结束，记录里不会留下批准项，操作也没有执行。
"""

import time
from collections.abc import Callable, Mapping
from pathlib import Path

from lime_star.agent_runtime import run_turn
from lime_star.model_provider import (
    Clock,
    NewId,
    Provider,
    RequestLog,
    load_config,
    new_id,
    utc_now,
)
from lime_star.model_provider.client import Client, open_client
from lime_star.model_provider.request_log import LOG_DIR
from lime_star.protocol import (
    Approval,
    Decision,
    Entry,
    Item,
    Model,
    Pending,
    TurnResult,
)
from lime_star.thread_store import Transcript
from lime_star.tool_runtime import Registry, default_tools

_WAIT_SLICE = 0.1
"""提问回调先返回、决定稍后才到的时候，按这个切片反复等：Ctrl+C 最多晚一个切片生效。"""

Show = Callable[[Entry], None]
"""显示回调：一项落盘后被调用一次，参数就是落盘后的这一项。终端显示只能从这里来。"""

Ask = Callable[[Pending], None]
"""提问回调：一次危险操作等待批准时被调用一次，参数是等待批准的操作。

它向用户提问，并用 respond_action 交回决定；也可以先返回，等用户决定之后再交回。
"""


class SessionError(Exception):
    """会话无法建立，或者回应的不是正在等待的批准。消息可以直接显示给用户。"""


class Session:
    """一次会话。状态只由调用 start_turn 的线程改写；respond_action 可以从别的线程调用。"""

    def __init__(
        self,
        model: Model,
        tools: Registry,
        transcript: Transcript,
        new_id: NewId = new_id,
    ) -> None:
        self._model = model
        self._tools = tools
        self._transcript = transcript
        self._new_id = new_id
        self._gate: _Gate | None = None

    def start_turn(
        self, text: str, *, show: Show | None = None, ask: Ask | None = None
    ) -> TurnResult:
        """提交一个回合：跑完它，返回这个回合的结局。

        给了 show 时，这个回合里每一项落盘后都被调用一次，参数是落盘后的这一项。
        给了 ask 时，危险操作执行前经它向用户提问；没有给，危险操作一律不执行。
        """
        turn_id = self._new_id()

        def journal(item: Item) -> Entry:
            entry = self._transcript.append(item, turn_id)
            if show is not None:
                show(entry)
            return entry

        def write(item: Item, _turn: str) -> Entry:
            return journal(item)

        gate = _Gate(journal, ask)
        self._gate = gate
        try:
            return run_turn(
                turn_id,
                self._transcript.read(),
                text,
                model=self._model,
                tools=self._tools.approved_by(gate.approve),
                journal=write,
            )
        finally:
            self._gate = None

    def read_thread(self) -> tuple[Entry, ...]:
        """到此刻为止的全部项，只凭会话记录的文件读回。"""
        return self._transcript.read()

    def respond_action(self, call_id: str, decision: Decision) -> None:
        """回应一次正在等待批准的危险操作（R7.6、R7.9）。CLI 和测试从这里交回用户的决定。"""
        if self._gate is None:
            raise SessionError("现在没有等待批准的操作。")
        self._gate.answer(call_id, decision)


class _Gate:
    """一个回合里等待批准的位置。状态只在内存里；落盘的只有用户做出决定之后的批准项。"""

    def __init__(self, journal: Callable[[Item], Entry], ask: Ask | None) -> None:
        self._journal = journal
        self._ask = ask
        self._pending: Pending | None = None
        self._decision: Decision | None = None

    def approve(self, pending: Pending) -> bool:
        """工具边界请求一次批准：提问，等决定，把决定写进会话记录，再交给工具。"""
        if self._ask is None:
            # 没有向用户提问的办法：拿不到批准就是拒绝。
            self._journal(Approval(pending.call_id, pending.name, pending.arguments, "rejected"))
            return False
        self._pending, self._decision = pending, None
        try:
            self._ask(pending)
            while (decision := self._decision) is None:
                time.sleep(_WAIT_SLICE)
        finally:
            self._pending, self._decision = None, None
        self._journal(Approval(pending.call_id, pending.name, pending.arguments, decision))
        return decision == "approved"

    def answer(self, call_id: str, decision: Decision) -> None:
        """respond_action 落到这里：决定交给正在等待的那次请求。对不上就拒绝，不放行。"""
        pending = self._pending
        if pending is None or pending.call_id != call_id:
            raise SessionError("没有在等待批准的操作，不能回应。")
        self._decision = decision


def open_session(
    *,
    env: Mapping[str, str],
    workdir: Path,
    client: Client | None = None,
    now: Clock = utc_now,
    new_id: NewId = new_id,
    tools: Registry | None = None,
) -> Session:
    """读取模型配置，建好请求日志和会话记录，接上模型边界和工具边界，返回一个新会话。

    client 留空时按配置构造；测试可以传入指向替身服务的客户端。
    tools 留空时是正式命令的工具集；测试可以传入自己的工具集。
    """
    config = load_config(env, workdir)
    session_id, thread_id = new_id(), new_id()
    try:
        log = RequestLog.at(workdir)
        transcript = Transcript.at(workdir, thread_id, now=now)
    except OSError as exc:
        runtime = LOG_DIR.parent
        raise SessionError(f"无法在工作目录下创建 {runtime}（{type(exc).__name__}）") from exc
    provider = Provider(
        client=client if client is not None else open_client(config),
        config=config,
        log=log,
        session_id=session_id,
        thread_id=thread_id,
        now=now,
        new_id=new_id,
    )
    chosen = tools if tools is not None else default_tools(workdir)
    return Session(provider, chosen, transcript, new_id)
