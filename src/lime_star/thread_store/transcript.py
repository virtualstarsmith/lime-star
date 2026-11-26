"""会话记录：一个会话一个 JSON Lines 文件，逐项追加、逐项落盘，只凭文件读回。

位置是工作目录下的 .lime-star/threads/<thread_id>.jsonl（决策 D-23、D-29）。
每一行是带信封的一项，形状由仓库根的 protocol/thread-items.schema.json 约定（契约 thread-items）。
边界以 internal/aiprompts/architecture.md 为准：这个模块只管一份会话记录的写入、读回和编码，
不放临时界面状态，也不在内存里保留第二份会话真相。工作目录下会话的查找、独占写入和回合的读模型
分别在 threads.py、hold.py、turns.py。
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import Field, asdict, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeGuard, get_args

from lime_star.protocol import ENVELOPE, ITEM_KINDS, Entry, Item, Outcome

THREADS_DIR = Path(".lime-star") / "threads"
SUFFIX = ".jsonl"

Clock = Callable[[], datetime]

_KINDS: dict[str, type[Item]] = {item_kind.kind: item_kind for item_kind in ITEM_KINDS}


def utc_now() -> datetime:
    return datetime.now(UTC)


class BrokenItem(ValueError):
    """会话记录里有一行看不懂。读的时候直接报错，不悄悄丢掉，也不回显那一行的内容。"""


class Transcript:
    """一个会话的会话记录。除了文件位置、会话标识和时钟，不保存任何状态。"""

    def __init__(self, path: Path, thread_id: str, now: Clock = utc_now) -> None:
        self._path = path
        self._thread_id = thread_id
        self._now = now

    @classmethod
    def at(cls, workdir: Path, thread_id: str, now: Clock = utc_now) -> Transcript:
        """为一个新会话准备记录：在工作目录下建好 .lime-star/threads。文件在写第一项时才出现。"""
        directory = workdir / THREADS_DIR
        directory.mkdir(parents=True, exist_ok=True)
        return cls(directory / f"{thread_id}{SUFFIX}", thread_id, now)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def thread_id(self) -> str:
        return self._thread_id

    def append(self, item: Item, turn_id: str) -> Entry:
        """追加一项并落盘，返回带信封的这一项。写不进去时抛 OSError。"""
        entry = Entry(self._written() + 1, self._now(), self._thread_id, turn_id, item)
        line = json.dumps(encode(entry), ensure_ascii=False) + "\n"
        with self._path.open("a", encoding="utf-8", newline="\n") as file:
            file.write(line)
            file.flush()
            os.fsync(file.fileno())
        return entry

    def _written(self) -> int:
        """文件里已经有多少项。末尾是半行时抛 BrokenItem：接着写会让新的一项和那半行连在一起。"""
        try:
            raw = self._path.read_bytes()
        except FileNotFoundError:
            return 0
        if raw and not raw.endswith(b"\n"):
            raise BrokenItem("会话记录的末尾是半行，不能接着写")
        return raw.count(b"\n")

    def read(self) -> tuple[Entry, ...]:
        """只凭文件读回这个会话的全部项，按写入顺序。"""
        return read(self._path)


def read(path: Path) -> tuple[Entry, ...]:
    """只凭一个记录文件读回全部的项，按写入顺序。文件还不存在时返回空元组。

    末尾没有换行的残行不算一项，所以进程被强制结束时留下的半行读不出来（R6.5）。
    """
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return ()
    complete = raw.split(b"\n")[:-1]
    return tuple(decode(line) for line in complete if line.strip())


def encode(entry: Entry) -> dict[str, Any]:
    """一项写成一行 JSON 的内容：信封的四个字段，项的类型名 type，然后是项自己的字段。"""
    record: dict[str, Any] = {
        "seq": entry.seq,
        "time": entry.time.isoformat(),
        "thread_id": entry.thread_id,
        "turn_id": entry.turn_id,
        "type": entry.item.kind,
    }
    record.update(asdict(entry.item))
    return record


def decode(line: bytes | str) -> Entry:
    """从一行 JSON 读出一项。类型不认识，或者字段多了、少了、对不上，都抛 BrokenItem。"""
    try:
        data = json.loads(line)
    except ValueError as exc:
        raise BrokenItem("不是合法的 JSON") from exc
    if not isinstance(data, dict):
        raise BrokenItem("不是 JSON 对象")
    seq = data.get("seq")
    when = data.get("time")
    thread_id = data.get("thread_id")
    turn_id = data.get("turn_id")
    if not _is_count(seq) or not (_is_text(when) and _is_text(thread_id) and _is_text(turn_id)):
        raise BrokenItem("信封的字段不对")
    try:
        moment = datetime.fromisoformat(when)
    except ValueError as exc:
        raise BrokenItem("时间不是 ISO 8601 的写法") from exc
    kind = _KINDS.get(str(data.get("type")))
    if kind is None:
        raise BrokenItem("看不懂的项类型")
    values: dict[str, Any] = {}
    for field in fields(kind):
        if field.name not in data:
            raise BrokenItem(f"{kind.__name__} 缺少字段 {field.name}")
        values[field.name] = _value(kind, field, data[field.name])
    extra = sorted(set(data) - set(ENVELOPE) - {"type"} - set(values))
    if extra:
        raise BrokenItem(f"{kind.__name__} 多出字段：{', '.join(extra)}")
    item = kind(**values)
    return Entry(seq, moment, thread_id, turn_id, item)


def _is_count(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _is_text(value: object) -> TypeGuard[str]:
    return isinstance(value, str) and bool(value)


def _value(kind: type[Item], field: Field[Any], raw: object) -> Any:
    """按数据类字段的声明核对 JSON 里的值；对不上时抛 BrokenItem。"""
    expected = field.type
    if expected is bool:
        ok = isinstance(raw, bool)
    elif expected is str:
        ok = isinstance(raw, str)
    elif expected is Outcome:
        ok = False
        if isinstance(raw, str):
            try:
                return Outcome(raw)
            except ValueError:
                pass
    else:
        choices = get_args(expected)
        ok = bool(choices) and raw in choices
    if not ok:
        raise BrokenItem(f"{kind.__name__} 的字段 {field.name} 类型不对")
    return raw
