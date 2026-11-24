"""会话的终端交互：横幅、输入提示、显示回复、Ctrl+C 与输入结束（需求 R13）。"""

import queue
import threading
from enum import Enum, auto
from pathlib import Path
from typing import Protocol, TextIO, assert_never

from lime_star import __version__
from lime_star.app import Outcome, Session, TurnResult

EXIT_OK = 0
EXIT_RUNTIME = 1

PROMPT = "你> "
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
        try:
            result = session.start_turn(text)
        except KeyboardInterrupt:
            continue  # 兜底：回合里的中断已经处理，回到输入提示（R13.11）
        _show(result, out, err)
        ignored = lines.drain()
        if ignored:
            _say(err, f"已忽略 {ignored} 行回合中收到的输入。\n")


def _show(result: TurnResult, out: TextIO, err: TextIO) -> None:
    match result.outcome:
        case Outcome.DONE:
            _say(out, result.reply.rstrip("\n") + "\n")
        case Outcome.CANCELLED:
            _say(out, "已取消。\n")
        case Outcome.STEP_LIMIT:
            # 达到上限不是错误，说明写在标准输出（R12.3）。
            _say(out, f"回合结束：{result.reason}。\n")
        case Outcome.ERROR:
            # 错误写标准错误（R13.5-S2），只写类别和状态码。
            _say(err, f"回合出错：{result.reason}。\n")
        case _:
            assert_never(result.outcome)


def _say(stream: TextIO, text: str) -> None:
    stream.write(text)
    stream.flush()
