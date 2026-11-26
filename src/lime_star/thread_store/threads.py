"""工作目录下的会话：找出最近一个有活动的会话（R9.1）。

会话放在哪里、怎样列出来是 thread_store 的事；app 回合入口和 CLI 只拿到会话标识。
活动以会话记录里最后一项的时间为准，这是记录里的事实。文件的修改时间不算：复制目录或还原文件会改变它。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from lime_star.protocol import Entry
from lime_star.thread_store.transcript import SUFFIX, THREADS_DIR, BrokenItem, decode


def latest(workdir: Path) -> str | None:
    """工作目录下最近一个有活动的会话的标识；一个都没有时返回 None。

    没有完整项的文件不算有活动。最后一项读不懂时抛 BrokenItem，说明是哪个文件：不悄悄跳过它
    去恢复另一个会话。
    """
    newest: tuple[datetime, str] | None = None
    for path in _transcripts(workdir):
        try:
            last = _last(path)
        except FileNotFoundError:
            continue  # 列出之后被删掉了
        if last is None:
            continue
        mark = (last.time, path.stem)
        if newest is None or mark > newest:
            newest = mark
    return None if newest is None else newest[1]


def _transcripts(workdir: Path) -> list[Path]:
    return sorted((workdir / THREADS_DIR).glob(f"*{SUFFIX}"))


def _last(path: Path) -> Entry | None:
    """文件里最后一项完整的项。末尾的半行不算（R6.5）。读不懂时说明是哪个文件。"""
    lines = path.read_bytes().split(b"\n")[:-1]
    if not lines or not lines[-1].strip():
        return None
    try:
        return decode(lines[-1])
    except BrokenItem as exc:
        raise BrokenItem(f"{path.name}：{exc}") from exc
