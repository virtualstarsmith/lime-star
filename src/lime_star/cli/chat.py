"""会话的终端交互：横幅、输入提示、把会话记录投影到终端、批准提示、Ctrl+C 与输入结束（需求 R13）。

终端上关于一个回合的每一行都来自会话记录：一项落盘后，project 把它显示出来。这里不留状态，
也不自己拼第二份会话真相。批准提示本身不是记录，它是向用户提的问题：说明由工具边界给出，
这里把它显示出来、读一行输入，再把决定交回 app 回合入口（R7.6 到 R7.9）。
"""

import queue
import threading
from enum import Enum, auto
from pathlib import Path
from typing import Protocol, TextIO, assert_never

from lime_star import __version__
from lime_star.app import Session
from lime_star.protocol import (
    Approval,
    Entry,
    ModelText,
    Outcome,
    Pending,
    Reasoning,
    ToolCall,
    ToolResult,
    TurnEnd,
    TurnStart,
    UserMessage,
)

EXIT_OK = 0
EXIT_RUNTIME = 1

PROMPT = "你> "
ASK = "[y/n] "
"""批准提示末尾的标记（决策 D-05）：界面文案是中文，给脚本识别的标记用 ASCII。"""
APPROVE = "y"
"""只有这一行输入算批准；别的输入、空输入、输入结束都算拒绝（R7.9，决策 D-20）。"""
EXIT_COMMAND = "/exit"

# 取输入时按这个切片反复等，理由同 model_provider 里的等待：
# 中断最多晚一个切片生效，有输入到达时等待立即返回。
_WAIT_SLICE = 0.1


class LineSource(Protocol):
    """一行输入的来源。next_line 在没有更多输入时返回 None。"""

    def next_line(self) -> str | None: ...

    def drain(self) -> int:
        """丢掉已经到达、还没取用的行，返回丢掉的行数。"""
        ...


class LineReader(Protocol):
    """StdinLines 需要的最小输入接口：能一行一行地读，读到末尾返回空串。"""

    def readline(self) -> str: ...


class InputError(Exception):
    """标准输入读不下去了。"""


class _Signal(Enum):
    EOF = auto()
    BROKEN = auto()


class StdinLines:
    """由后台线程持续读标准输入，行进入队列，主线程决定何时取用。

    回合进行中到达的行留在队列里，回合结束时由 drain 丢弃（R13.8、R13.9，决策 D-06）。
    批准提示出现之前到达的行也一样，在显示提示之前就丢掉：没有看到提示就给出的回答不算批准。
    输入结束或读不下去是永久状态：第一次看到之后，再取输入立刻给出同样的结果，不会一直等。

    读取经由传入的文本流进行（生产里是 sys.stdin），实例也一直持有它。进程收尾时，解释器
    若去关闭一个被后台线程占着的缓冲流，CPython 会报致命错误；这个引用让 sys.stdin 一直
    活到进程结束，不会被关闭。不要改成直接读 sys.stdin.buffer。
    """

    def __init__(self, stream: LineReader) -> None:
        self._queue: queue.Queue[str | _Signal] = queue.Queue()
        self._stream = stream
        self._signal: _Signal | None = None

    def start(self) -> None:
        threading.Thread(target=self._pump, name="stdin", daemon=True).start()

    def next_line(self) -> str | None:
        """取下一行。输入结束之后返回 None，读不下去时抛 InputError。"""
        if self._signal is _Signal.BROKEN:
            raise InputError
        if self._signal is _Signal.EOF:
            return None
        item = self._take()
        if isinstance(item, _Signal):
            self._signal = item
            return self.next_line()
        return item

    def drain(self) -> int:
        ignored = 0
        signal: _Signal | None = None
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            if isinstance(item, _Signal):
                signal = item
            else:
                ignored += 1
        if signal is not None:
            self._queue.put(signal)
        return ignored

    def _take(self) -> str | _Signal:
        while True:
            try:
                return self._queue.get(timeout=_WAIT_SLICE)
            except queue.Empty:
                continue

    def _pump(self) -> None:
        while True:
            try:
                line = self._stream.readline()
            except (OSError, ValueError):
                self._queue.put(_Signal.BROKEN)
                return
            if line == "":
                self._queue.put(_Signal.EOF)
                return
            self._queue.put(line)


def chat(session: Session, lines: LineSource, out: TextIO, err: TextIO, workdir: Path) -> int:
    """跑一次会话，返回进程退出码。"""
    _say(out, f"lime-star {__version__}  {workdir}\n")
    while True:
        _say(out, PROMPT)
        try:
            line = lines.next_line()
        except KeyboardInterrupt:
            return EXIT_OK  # R13.12：输入提示处的 Ctrl+C 结束会话
        except InputError:
            _say(err, "标准输入无法读取，会话结束。\n")
            return EXIT_RUNTIME
        if line is None:
            return EXIT_OK  # R13.13：输入结束
        text = line.strip()
        if not text:
            continue  # R13.3：空行被忽略
        if text == EXIT_COMMAND:
            return EXIT_OK  # R13.4
        dropped = 0

        def ask(pending: Pending) -> None:
            """向用户发起一次批准：显示说明，读一行，把决定交回 app（R7.6 到 R7.9）。"""
            nonlocal dropped
            # 提示出现之前到达的输入不是对它的回应：按回合中的输入丢弃（R13.8）。
            dropped += lines.drain()
            _say(out, pending.note + "\n")
            _say(out, ASK)
            try:
                answer = lines.next_line()
            except InputError:
                answer = None  # 读不到输入就没有批准
            granted = answer is not None and answer.strip() == APPROVE
            session.respond_action(pending.call_id, "approved" if granted else "rejected")

        try:
            session.start_turn(text, show=lambda entry: project(entry, out, err), ask=ask)
        except KeyboardInterrupt:
            continue  # 兜底：回合里的中断已经处理，回到输入提示（R13.11）
        ignored = dropped + lines.drain()
        if ignored:
            _say(err, f"已忽略 {ignored} 行回合中收到的输入。\n")


def project(entry: Entry, out: TextIO, err: TextIO) -> None:
    """把会话记录里的一项显示在终端上（需求 R13.14、R13.15）。

    显示是记录的投影：只看传进来的这一项，不留状态。不显示的项什么都不输出。
    """
    match entry.item:
        case ModelText():
            _say(out, entry.item.content.rstrip("\n") + "\n")
        case ToolCall():
            _say(out, f"调用 {entry.item.name} {entry.item.arguments}\n")
        case ToolResult():
            summary = entry.item.summary or entry.item.content.split("\n")[0]
            _say(out, f"结果出错：{summary}\n" if entry.item.error else f"结果：{summary}\n")
        case Approval():
            _say(out, "已批准。\n" if entry.item.decision == "approved" else "已拒绝。\n")
        case TurnEnd():
            _ending(entry.item, out, err)
        case UserMessage() | Reasoning() | TurnStart():
            pass
        case _:
            assert_never(entry.item)


def _ending(end: TurnEnd, out: TextIO, err: TextIO) -> None:
    """回合的结局：完成时不另输出；取消和步数上限不是错误，写标准输出；出错写标准错误（R13.5-S2）。"""
    match end.outcome:
        case Outcome.DONE:
            pass
        case Outcome.CANCELLED:
            _say(out, "已取消。\n")
        case Outcome.STEP_LIMIT:
            _say(out, f"回合结束：{end.reason}。\n")
        case Outcome.ERROR:
            # 只写类别和状态码。
            _say(err, f"回合出错：{end.reason}。\n")
        case _:
            assert_never(end.outcome)


def _say(stream: TextIO, text: str) -> None:
    stream.write(text)
    stream.flush()
