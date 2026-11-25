"""持久化：会话记录的追加写入、读回与编码。

边界以 internal/aiprompts/architecture.md 为准：这里是会话记录（transcript）的唯一 owner，
不放临时界面状态，也不在内存里保留第二份会话真相。
"""

from lime_star.thread_store.transcript import (
    THREADS_DIR,
    BrokenItem,
    Transcript,
    decode,
    encode,
    read,
)

__all__ = ["BrokenItem", "THREADS_DIR", "Transcript", "decode", "encode", "read"]
