"""真实进程里的 lime-star --resume：两个进程先后在同一个工作目录里运行。

证据等级：Gate B，真实进程、真实输入、贯穿主链的可见输出。模型是测试替身（本地替身服务，
脚本化响应，没有从真实运行录制），不是真实模型。断言同时看终端输出、会话记录文件和请求日志。
覆盖 R9.1、R9.2-S1、R9.3-S2、R9.4-S1、R9.5-S2、R3.4，以及"一个会话同一时刻只有一个写入者"。
真实控制台上的 Ctrl+C 之后的恢复在 test_cli_console.py；回放夹具和真实模型在冒烟脚本
scripts/smoke/resume_gate_b.py。
"""

import json
from collections.abc import Callable
from pathlib import Path

from lime_star import __version__
from lime_star.app import Outcome
from lime_star.cli.chat import ASK, PROMPT
from lime_star.model_provider import API_KEY_VAR, BASE_URL_VAR, MODEL_VAR
from lime_star.protocol import ToolResult, TurnEnd
from lime_star.thread_store.turns import NOT_CLOSED, WAITING
from tests.integration.fake_model import FAKE_MODEL, FakeModel
from tests.integration.support import (
    CliProcess,
    entries_of,
    kill_tree,
    kinds,
    lines_of,
    read_log,
    transcript_file,
    transcript_files,
    wait_released,
    written,
)

WRITE_HELLO = json.dumps({"path": "hello.py", "content": "print('hello')\n"})


def banner(workdir: Path) -> str:
    return f"lime-star {__version__}  {workdir}\n"


def test_resume_without_a_session_exits_two(
    start_cli: Callable[..., CliProcess], tmp_path: Path
) -> None:
    """R9.1-S2：工作目录下没有会话时退出码为 2，标准错误说明没有可恢复的会话。

    这里故意不给模型配置：没有会话时，提示的是真正缺的东西。运行时目录没有建。
    """
    process = start_cli(None, ["--resume"])
    assert process.finish() == 2
    assert (process.output("stdout"), process.output("stderr")) == (
        "",
        "lime-star：工作目录下没有可恢复的会话。\n",
    )
    assert list(tmp_path.iterdir()) == []


def test_a_new_process_resumes_the_history_and_goes_on(
    start_cli: Callable[..., CliProcess],
    model_env: dict[str, str],
    fake_model: FakeModel,
    log_path: Path,
    tmp_path: Path,
) -> None:
    """R9.1、R9.2-S1、R9.5-S2、R3.4：新进程恢复历史并继续对话。

    终端只多了一行说明，之前的输出不重放；模型收到恢复之前的问答；请求日志带新的会话标识
    和原来的线程标识。
    """
    fake_model.reply("好的，小星。")
    first = start_cli(model_env)
    first.wait_for("stdout", PROMPT)
    first.send("你好，我叫小星")
    first.wait_for("stdout", PROMPT, count=2)
    first.send("/exit")
    assert first.finish() == 0
    [path] = transcript_files(tmp_path)

    fake_model.reply("小星。")
    second = start_cli(model_env, ["--resume"])
    second.wait_for("stdout", PROMPT)
    assert second.output("stdout") == (
        banner(tmp_path) + f"已恢复会话 {path.stem}，已有 1 个回合。\n" + PROMPT
    )
    second.send("我刚才说的名字是什么？")
    second.wait_for("stdout", PROMPT, count=2)
    second.send("/exit")
    assert second.finish() == 0
    assert second.output("stdout") == (
        banner(tmp_path)
        + f"已恢复会话 {path.stem}，已有 1 个回合。\n"
        + PROMPT
        + "小星。\n"
        + PROMPT
    )
    assert (second.output("stderr"), transcript_files(tmp_path)) == ("", [path])

    [old, new] = fake_model.requests()
    assert [message["content"] for message in new.messages[1:]] == [
        "你好，我叫小星",
        "好的，小星。",
        "我刚才说的名字是什么？",
    ]
    assert len(old.messages) == 2
    [before, after] = read_log(log_path)
    assert before["session_id"] != after["session_id"]
    assert [before["thread_id"], after["thread_id"]] == [path.stem, path.stem]


def test_resume_picks_the_last_session_that_was_active(
    start_cli: Callable[..., CliProcess],
    model_env: dict[str, str],
    fake_model: FakeModel,
    tmp_path: Path,
) -> None:
    """R9.1-S1：工作目录下有两个会话，--resume 恢复最后有活动的那个。"""
    fake_model.reply("第一答")
    first = start_cli(model_env)
    first.wait_for("stdout", PROMPT)
    first.send("甲的问题")
    first.wait_for("stdout", PROMPT, count=2)
    first.send("/exit")
    assert first.finish() == 0
    fake_model.reply("第二答")
    second = start_cli(model_env)
    second.wait_for("stdout", PROMPT)
    second.send("乙的问题")
    second.wait_for("stdout", PROMPT, count=2)
    second.send("/exit")
    assert second.finish() == 0
    files = transcript_files(tmp_path)
    assert len(files) == 2

    fake_model.reply("接着答")
    third = start_cli(model_env, ["--resume"])
    third.wait_for("stdout", PROMPT)
    [latest] = [
        path for path in files if any(line.get("content") == "乙的问题" for line in lines_of(path))
    ]
    assert f"已恢复会话 {latest.stem}，已有 1 个回合。\n" in third.output("stdout")
    third.send("接着问")
    third.wait_for("stdout", PROMPT, count=2)
    third.send("/exit")
    assert third.finish() == 0
    [_, _, request] = fake_model.requests()
    said = [message["content"] for message in request.messages[1:]]
    assert "乙的问题" in said and "甲的问题" not in said


def test_resume_after_the_process_was_killed_at_the_prompt(
    start_cli: Callable[..., CliProcess],
    model_env: dict[str, str],
    fake_model: FakeModel,
    tmp_path: Path,
) -> None:
    """R9.3-S2、R9.4-S1：批准提示出现之后进程被强制结束，谁也没有回应。

    新进程 --resume：说明上一个回合没有完成，原因写明当时在等待批准、操作没有执行。
    没有续跑：没有批准提示，模型没有被再次请求，文件也没有被写。记录里那个回合有了结果和中断结局，
    接着对话时模型看得到那条结果。
    """
    fake_model.call(("write_file", json.loads(WRITE_HELLO)))
    first = start_cli(model_env)
    first.wait_for("stdout", PROMPT)
    first.send("新建 hello.py")
    first.wait_for("stdout", ASK)
    kill_tree(first.process)
    first.close()
    path = transcript_file(tmp_path)
    wait_released(tmp_path, path.stem)
    assert kinds(entries_of(path)) == ["turn_start", "user_message", "tool_call"]
    assert not (tmp_path / "hello.py").exists()

    fake_model.reply("没有写。")
    second = start_cli(model_env, ["--resume"])
    second.wait_for("stdout", PROMPT)
    reason = f"{NOT_CLOSED}，当时正在等待批准 write_file，这次操作没有执行"
    assert second.output("stdout") == (
        banner(tmp_path)
        + f"已恢复会话 {path.stem}，已有 1 个回合。\n"
        + f"上一个回合没有完成：{reason}。\n"
        + PROMPT
    )
    assert (ASK in second.output("stdout"), len(fake_model.requests())) == (False, 1)
    assert not (tmp_path / "hello.py").exists()
    assert written(entries_of(path))[-2:] == (
        ToolResult("call1", WAITING, True, WAITING),
        TurnEnd(Outcome.INTERRUPTED, reason),
    )

    second.send("hello.py 写好了吗？")
    second.wait_for("stdout", PROMPT, count=2)
    second.send("/exit")
    assert second.finish() == 0
    assert second.output("stderr") == ""
    assert not (tmp_path / "hello.py").exists()
    [_, request] = fake_model.requests()
    assert [message["content"] for message in request.messages[1:]] == [
        "新建 hello.py",
        None,
        WAITING,
        "hello.py 写好了吗？",
    ]


def test_resume_is_refused_while_the_session_is_still_open(
    start_cli: Callable[..., CliProcess],
    model_env: dict[str, str],
    fake_model: FakeModel,
    tmp_path: Path,
) -> None:
    """一个会话记录同一时刻只有一个写入者：那个会话的进程还开着，--resume 以 1 退出并说明原因；
    开着的那个会话不受影响。"""
    fake_model.reply("答")
    first = start_cli(model_env)
    first.wait_for("stdout", PROMPT)
    first.send("问")
    first.wait_for("stdout", PROMPT, count=2)
    path = transcript_file(tmp_path)
    second = start_cli(model_env, ["--resume"])
    assert second.finish() == 1
    assert (second.output("stdout"), second.output("stderr")) == (
        "",
        f"lime-star：会话 {path.stem} 正被另一个进程使用，现在不能恢复。\n",
    )
    first.send("/exit")
    assert first.finish() == 0


def test_resume_with_a_missing_config_exits_two(
    start_cli: Callable[..., CliProcess],
    model_env: dict[str, str],
    fake_model: FakeModel,
    tmp_path: Path,
) -> None:
    """R9.5、R4.2：模型配置不随会话保存；恢复时缺配置照样拒绝启动，点名缺的变量，不发请求。"""
    fake_model.reply("答")
    first = start_cli(model_env)
    first.wait_for("stdout", PROMPT)
    first.send("问")
    first.wait_for("stdout", PROMPT, count=2)
    first.send("/exit")
    assert first.finish() == 0
    second = start_cli({BASE_URL_VAR: fake_model.url, MODEL_VAR: FAKE_MODEL}, ["--resume"])
    assert second.finish() == 2
    assert API_KEY_VAR in second.output("stderr")
    assert second.output("stdout") == ""
    assert len(fake_model.requests()) == 1
