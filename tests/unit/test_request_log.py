"""RequestLog 的单元测试：逐行追加、并发不交错、目录建在工作目录下（R3.1，决策 D-29）。"""

import json
import threading
from pathlib import Path

from lime_star.model_provider import RequestLog


def test_at_creates_log_directory_under_workdir(tmp_path: Path) -> None:
    """决策 D-29：运行时数据放在工作目录下的 .lime-star/。"""
    log = RequestLog.at(tmp_path)
    assert log.path == tmp_path / ".lime-star" / "logs" / "requests.jsonl"
    assert log.path.parent.is_dir()
    assert not log.path.exists()


def test_each_record_is_one_json_line_in_order(tmp_path: Path) -> None:
    log = RequestLog.at(tmp_path)
    log.append({"request_id": "a", "status": "ok"})
    log.append({"request_id": "b", "status": "failed"})
    assert log.path.read_text(encoding="utf-8") == (
        '{"request_id": "a", "status": "ok"}\n{"request_id": "b", "status": "failed"}\n'
    )


def test_non_ascii_is_written_as_utf8(tmp_path: Path) -> None:
    log = RequestLog.at(tmp_path)
    log.append({"model": "模型-甲"})
    assert '"model": "模型-甲"' in log.path.read_bytes().decode("utf-8")


def test_concurrent_appends_do_not_interleave(tmp_path: Path) -> None:
    """被放弃的请求会晚到，它的记录不能和别的记录写在一行里。"""
    log = RequestLog.at(tmp_path)

    def worker(number: int) -> None:
        for index in range(20):
            log.append({"worker": number, "index": index, "pad": "x" * 200})

    threads = [threading.Thread(target=worker, args=(number,)) for number in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert not any(thread.is_alive() for thread in threads)
    lines = log.path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 160
    assert [json.loads(line)["pad"] for line in lines] == ["x" * 200] * 160
