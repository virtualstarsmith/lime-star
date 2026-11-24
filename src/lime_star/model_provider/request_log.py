"""请求日志：每次模型请求追加一行 JSON（需求 R3.1 到 R3.3，决策 D-09）。"""

from __future__ import annotations

import json
import threading
from collections.abc import Mapping
from pathlib import Path

LOG_DIR = Path(".lime-star") / "logs"
REQUEST_LOG = "requests.jsonl"


class RequestLog:
    """请求日志文件。追加一行加一次锁，被放弃的请求晚到的记录不会交错。"""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()

    @classmethod
    def at(cls, workdir: Path) -> RequestLog:
        """在工作目录下建好 .lime-star/logs。建不了时抛 OSError。"""
        path = workdir / LOG_DIR / REQUEST_LOG
        path.parent.mkdir(parents=True, exist_ok=True)
        return cls(path)

    @property
    def path(self) -> Path:
        return self._path

    def append(self, record: Mapping[str, object]) -> None:
        line = json.dumps(record, ensure_ascii=False) + "\n"
        with self._lock:
            with self._path.open("a", encoding="utf-8") as file:
                file.write(line)
