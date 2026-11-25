"""回合入口：建立会话、提交回合、读取会话记录。

这里把循环、模型边界、工具边界和会话记录装配起来，回合本身由 agent_runtime 的循环跑完。
会话记录由 thread_store 持有：它是会话的唯一事实源，这里不在内存里留第二份。
"""

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
from lime_star.protocol import Entry, Item, Model, ToolSet, TurnResult
from lime_star.thread_store import Transcript
from lime_star.tool_runtime import default_tools

Show = Callable[[Entry], None]
"""显示回调：一项落盘后被调用一次，参数就是落盘后的这一项。终端显示只能从这里来。"""


class SessionError(Exception):
    """会话无法建立。消息可以直接显示给用户。"""


class Session:
    """一次会话。状态只由调用 start_turn 的线程改写。"""

    def __init__(
        self,
        model: Model,
        tools: ToolSet,
        transcript: Transcript,
        new_id: NewId = new_id,
    ) -> None:
        self._model = model
        self._tools = tools
        self._transcript = transcript
        self._new_id = new_id

    def start_turn(self, text: str, *, show: Show | None = None) -> TurnResult:
        """提交一个回合：跑完它，返回这个回合的结局。

        给了 show 时，这个回合里每一项落盘后都被调用一次，参数是落盘后的这一项。
        """
        turn_id = self._new_id()

        def journal(item: Item, turn: str) -> Entry:
            entry = self._transcript.append(item, turn)
            if show is not None:
                show(entry)
            return entry

        return run_turn(
            turn_id,
            self._transcript.read(),
            text,
            model=self._model,
            tools=self._tools,
            journal=journal,
        )

    def read_thread(self) -> tuple[Entry, ...]:
        """到此刻为止的全部项，只凭会话记录的文件读回。"""
        return self._transcript.read()


def open_session(
    *,
    env: Mapping[str, str],
    workdir: Path,
    client: Client | None = None,
    now: Clock = utc_now,
    new_id: NewId = new_id,
    tools: ToolSet | None = None,
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
