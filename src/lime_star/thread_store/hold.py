"""会话记录的独占写入：一个会话同一时刻只有一个写入者。

打开会话（新建或恢复）时在工作目录下的 .lime-star/locks/<thread_id>.lock 上取一个操作系统的文件锁，
进程结束时自动释放，被强制结束也不例外。恢复时取不到，说明那个会话的进程还活着：这时恢复会让两个进程
写同一份记录，恢复的一方还会替一个正在进行的回合收尾，所以拒绝。

锁加在旁边的锁文件上，不加在会话记录文件上：Windows 上被锁住的字节别的句柄读不了，
而会话记录在会话进行中也要能被读（测试和 Gate A 都这样做）。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import BinaryIO

LOCKS_DIR = Path(".lime-star") / "locks"
SUFFIX = ".lock"


class Busy(Exception):
    """这个会话正被另一个进程使用。"""


class Hold:
    """对一个会话记录的独占写入。拿到之后一直持有，直到 release 或进程结束。"""

    def __init__(self, path: Path) -> None:
        self._file: BinaryIO | None = open(path, "a+b")
        try:
            _lock(self._file)
        except OSError as exc:
            self.release()
            raise Busy from exc

    @classmethod
    def take(cls, workdir: Path, thread_id: str) -> Hold:
        """为一个会话取独占写入：建好 .lime-star/locks。取不到时抛 Busy，建不了目录时抛 OSError。"""
        directory = workdir / LOCKS_DIR
        directory.mkdir(parents=True, exist_ok=True)
        return cls(directory / f"{thread_id}{SUFFIX}")

    def release(self) -> None:
        """放开独占写入。只在没有回合进行时调用：回合进行中放开，另一个进程就能进来写。"""
        if self._file is not None:
            self._file.close()  # 关掉句柄，锁随之放开
            self._file = None


def _lock(file: BinaryIO) -> None:
    """锁住锁文件的第 1 个字节，不等待；已经被别的进程锁着时抛 OSError。"""
    if sys.platform == "win32":
        import msvcrt

        file.seek(0)
        msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
