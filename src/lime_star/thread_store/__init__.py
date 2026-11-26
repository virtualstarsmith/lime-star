"""持久化：会话记录的追加写入、读取与读模型，会话的查找与独占写入。

边界以 internal/aiprompts/architecture.md 为准：这里是会话记录（transcript）的唯一 owner，
不放临时界面状态，也不在内存里保留第二份会话真相。恢复会话只从这里读回（需求 R9）。
"""

from lime_star.thread_store.hold import LOCKS_DIR, Busy, Hold
from lime_star.thread_store.threads import latest
from lime_star.thread_store.transcript import (
    THREADS_DIR,
    BrokenItem,
    Transcript,
    decode,
    encode,
    read,
)
from lime_star.thread_store.turns import Interrupted, interrupted, last_reason, turn_count

__all__ = [
    "LOCKS_DIR",
    "THREADS_DIR",
    "BrokenItem",
    "Busy",
    "Hold",
    "Interrupted",
    "Transcript",
    "decode",
    "encode",
    "interrupted",
    "last_reason",
    "latest",
    "read",
    "turn_count",
]
