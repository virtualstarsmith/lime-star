"""真实进程里的 lime-star 命令。

P0 的用例覆盖 R1.1 到 R1.3。P1 的用例通过管道驱动一个真实的会话进程。
发下一行之前等的是输入提示，不是回复文本：回复在它写进会话记录时就显示，
从回复出现到回合返回之间到达的输入按 R13.8 被丢弃。
证据等级：Gate B，真实进程、真实输入、贯穿主链的可见输出。模型是测试替身
（本地替身服务，脚本化响应，没有从真实运行录制），不是真实模型。
覆盖 R3.1、R3.2-S1、R4.1-S1、R4.2-S1、R4.3-S1、R4.3-S2、R13.1-S1、R13.2-S1、
R13.3-S1、R13.4-S1、R13.5、R13.6-S1、R13.7-S1、R13.8-S1、R13.9-S1、R13.10、R13.13-S1。
路线图 P2 加入 R12.3：达到步数上限时的终端说明。路线图 P5 加入 R9.1-S3（帮助里的 --resume）；
真实进程里的恢复在 test_cli_resume.py。
路线图 P4 加入批准提示：R7.6 到 R7.11、R7.13 里真实进程的部分。断言同时看终端输出和会话记录文件。
"""

import json
import socket
import subprocess
from collections.abc import Callable
from pathlib import Path

from lime_star import __version__
from tests.integration.fake_model import FAKE_KEY, FAKE_MODEL, FakeModel, Hold, error_body
from tests.integration.support import (
    PROMPT,
    RECORD_KEYS,
    CliProcess,
    child_env,
    read_log,
    run_lime_star,
    transcript_file,
)


def banner_line(output: str) -> str:
    return output.splitlines()[0]


def test_version_prints_one_line_and_exits_zero(lime_star: Path, tmp_path: Path) -> None:
    """R1.1-S1：标准输出只有版本这一行，退出码为 0。"""
    result = run_lime_star(lime_star, ["--version"], tmp_path)
    assert result.returncode == 0
    assert result.stdout.splitlines() == [f"lime-star {__version__}"]
    assert result.stderr == ""


def test_version_works_without_model_config(lime_star: Path, tmp_path: Path) -> None:
    """R1.1-S2：工作目录里没有模型配置，查版本仍然成功。"""
    assert list(tmp_path.iterdir()) == []
    result = run_lime_star(lime_star, ["--version"], tmp_path)
    assert result.returncode == 0
    assert result.stdout.splitlines() == [f"lime-star {__version__}"]


def test_help_lists_version_with_description(lime_star: Path, tmp_path: Path) -> None:
    """R1.2-S1：帮助里有 --version 和一句话说明，退出码为 0。"""
    result = run_lime_star(lime_star, ["--help"], tmp_path)
    assert result.returncode == 0
    assert "--version    显示版本号并退出" in result.stdout
    assert "不带参数：在工作目录开始一个会话" in result.stdout
    assert result.stderr == ""


def test_help_lists_resume(lime_star: Path, tmp_path: Path) -> None:
    """R9.1-S3、R1.2：--resume 已交付，帮助里有它和一句话说明。"""
    result = run_lime_star(lime_star, ["--help"], tmp_path)
    assert result.returncode == 0
    assert "--resume     恢复工作目录下最近的会话并继续对话" in result.stdout
    assert result.stderr == ""


def test_unknown_argument_exits_two_and_names_it(lime_star: Path, tmp_path: Path) -> None:
    """R1.3-S1：退出码为 2，标准错误指明未知的参数，标准输出为空。"""
    result = run_lime_star(lime_star, ["--nosuch"], tmp_path)
    assert result.returncode == 2
    assert "--nosuch" in result.stderr
    assert result.stdout == ""


def test_session_shows_version_and_workdir_then_exits_on_command(
    start_cli: Callable[..., CliProcess], model_env: dict[str, str], tmp_path: Path
) -> None:
    """R13.1-S1、R13.4-S1、R13.10-S1：一行版本号和工作目录、输入提示；/exit 以 0 结束。"""
    process = start_cli(model_env)
    process.wait_for("stdout", PROMPT)
    process.send("/exit")
    assert process.finish() == 0
    assert process.output("stdout").startswith(f"lime-star {__version__}  ")
    shown = Path(banner_line(process.output("stdout")).split("  ", 1)[1])
    assert shown.samefile(tmp_path)
    assert process.output("stdout").endswith(PROMPT)
    assert process.output("stderr") == ""


def test_message_goes_to_the_configured_model_and_reply_is_shown(
    start_cli: Callable[..., CliProcess],
    model_env: dict[str, str],
    fake_model: FakeModel,
    log_path: Path,
) -> None:
    """R13.2-S1、R13.5-S1、R13.7-S1、R4.1-S1：消息发给配置的模型，回复出现在标准输出。"""
    fake_model.reply("你好，我是替身模型。")
    process = start_cli(model_env)
    process.wait_for("stdout", PROMPT)
    process.send("你好")
    process.wait_for("stdout", "你好，我是替身模型。\n")
    process.wait_for("stdout", PROMPT, count=2)
    process.send("/exit")
    assert process.finish() == 0
    [request] = fake_model.requests()
    assert request.path == "/chat/completions"
    assert request.model == FAKE_MODEL
    assert request.authorization == f"Bearer {FAKE_KEY}"
    assert [message["role"] for message in request.messages] == ["system", "user"]
    assert request.messages[1]["content"] == "你好"
    assert process.output("stderr") == ""
    assert "\x1b" not in process.output("stdout")
    assert [record["status"] for record in read_log(log_path)] == ["ok"]


def test_chinese_output_redirected_to_a_file_is_utf8(
    lime_star: Path, model_env: dict[str, str], fake_model: FakeModel, tmp_path: Path
) -> None:
    """R13.6-S1：标准输出重定向到文件时，文件是合法的 UTF-8，中文不乱码。"""
    fake_model.reply("中文回复：你好，世界。")
    out_path = tmp_path / "stdout.txt"
    with out_path.open("wb") as out:
        result = subprocess.run(
            [str(lime_star)],
            cwd=tmp_path,
            env=child_env(model_env),
            input="你好\n/exit\n".encode(),
            stdout=out,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
    assert result.returncode == 0
    text = out_path.read_bytes().decode("utf-8")
    assert "中文回复：你好，世界。" in text
    assert "\ufffd" not in text


def test_missing_config_exits_two_and_names_the_variable(
    start_cli: Callable[..., CliProcess], fake_model: FakeModel, tmp_path: Path
) -> None:
    """R4.2-S1：缺少 LIME_STAR_API_KEY 时以 2 退出并点名它，不发模型请求，也不建运行时目录。"""
    process = start_cli({"LIME_STAR_BASE_URL": fake_model.url, "LIME_STAR_MODEL": FAKE_MODEL})
    assert process.finish() == 2
    assert process.output("stdout") == ""
    stderr = process.output("stderr")
    assert stderr == (
        "lime-star：缺少模型配置：LIME_STAR_API_KEY。"
        "请设置这些环境变量，或在 .env 里填写（样例见 .env.example）。\n"
    )
    assert fake_model.requests() == []
    assert list(tmp_path.iterdir()) == []


def test_env_file_in_the_workdir_supplies_the_config(
    start_cli: Callable[..., CliProcess], fake_model: FakeModel, tmp_path: Path
) -> None:
    """决策 D-01、R4.1：环境变量缺项时读工作目录下的 .env。"""
    tmp_path.joinpath(".env").write_text(
        f"LIME_STAR_BASE_URL={fake_model.url}\n"
        f"LIME_STAR_API_KEY={FAKE_KEY}\n"
        f"LIME_STAR_MODEL={FAKE_MODEL}\n",
        encoding="utf-8",
    )
    fake_model.reply("来自 .env 的配置也能用。")
    process = start_cli()
    process.wait_for("stdout", PROMPT)
    process.send("你好")
    process.wait_for("stdout", "来自 .env 的配置也能用。\n")
    process.wait_for("stdout", PROMPT, count=2)
    process.send("/exit")
    assert process.finish() == 0
    [request] = fake_model.requests()
    assert (request.model, request.authorization) == (FAKE_MODEL, f"Bearer {FAKE_KEY}")


def test_key_stays_out_of_terminal_and_log_even_if_the_api_echoes_it(
    start_cli: Callable[..., CliProcess],
    model_env: dict[str, str],
    fake_model: FakeModel,
    log_path: Path,
) -> None:
    """R4.3-S1、R4.3-S2、R13.5-S2、R13.10-S2：接口在错误正文里回显密钥，终端和日志里也搜不到它。

    回合出错写标准错误；进程本身没有出错，之后正常退出时退出码仍是 0。
    """
    fake_model.fail(401, error_body(f"Incorrect API key provided: {FAKE_KEY}"))
    fake_model.reply("第二次成功。")
    process = start_cli(model_env)
    process.wait_for("stdout", PROMPT)
    process.send("第一问")
    process.wait_for("stderr", "回合出错：鉴权失败（HTTP 401）。\n")
    process.wait_for("stdout", PROMPT, count=2)
    process.send("第二问")
    process.wait_for("stdout", "第二次成功。\n")
    process.wait_for("stdout", PROMPT, count=3)
    process.send("/exit")
    assert process.finish() == 0
    assert process.output("stderr") == "回合出错：鉴权失败（HTTP 401）。\n"
    assert process.output("stdout").count(PROMPT) == 3
    records = read_log(log_path)
    assert [record["status"] for record in records] == ["failed", "ok"]
    assert records[0]["error"] == {"kind": "auth", "status_code": 401, "detail": ""}
    for text in (process.output("stdout"), process.output("stderr"), log_path.read_text("utf-8")):
        assert FAKE_KEY not in text
        assert "Incorrect API key" not in text


def test_input_during_a_turn_is_dropped_and_reported(
    start_cli: Callable[..., CliProcess], model_env: dict[str, str], fake_model: FakeModel
) -> None:
    """R13.8-S1、R13.9-S1：回合进行中的两行输入不进入会话，回合结束后提示忽略了两行。"""
    hold = Hold()
    fake_model.reply("第一答", hold=hold)
    fake_model.reply("第二答")
    process = start_cli(model_env)
    process.wait_for("stdout", PROMPT)
    process.send("第一问")
    fake_model.wait_for_requests(1)
    process.send("被丢弃甲")
    process.send("被丢弃乙")
    hold.release()
    process.wait_for("stdout", "第一答\n")
    process.wait_for("stderr", "已忽略 2 行回合中收到的输入。\n")
    process.wait_for("stdout", PROMPT, count=2)
    process.send("第二问")
    process.wait_for("stdout", "第二答\n")
    process.wait_for("stdout", PROMPT, count=3)
    process.send("/exit")
    assert process.finish() == 0
    [first, second] = fake_model.requests()
    assert first.messages[1]["content"] == "第一问"
    assert [message["content"] for message in second.messages[1:]] == [
        "第一问",
        "第一答",
        "第二问",
    ]
    assert process.output("stderr") == "已忽略 2 行回合中收到的输入。\n"


def test_blank_lines_do_not_start_a_turn(
    start_cli: Callable[..., CliProcess], model_env: dict[str, str], fake_model: FakeModel
) -> None:
    """R13.3-S1：只按回车不开始回合，继续等待输入。"""
    fake_model.reply("答")
    process = start_cli(model_env)
    process.wait_for("stdout", PROMPT)
    process.send("")
    process.send("   ")
    process.wait_for("stdout", PROMPT, count=3)
    process.send("问")
    process.wait_for("stdout", "答\n")
    process.wait_for("stdout", PROMPT, count=4)
    process.send("/exit")
    assert process.finish() == 0
    assert len(fake_model.requests()) == 1


def test_closed_input_ends_the_session_with_zero(
    start_cli: Callable[..., CliProcess], model_env: dict[str, str], fake_model: FakeModel
) -> None:
    """R13.13-S1：标准输入关闭后，正在进行的回合照常完成，会话以 0 退出。"""
    fake_model.reply("答")
    process = start_cli(model_env)
    process.wait_for("stdout", PROMPT)
    process.send("问")
    process.close_input()
    process.wait_for("stdout", "答\n")
    assert process.finish() == 0
    assert process.output("stdout").endswith("答\n" + PROMPT)
    assert process.output("stderr") == ""


def test_unreachable_model_is_reported_and_not_retried(
    start_cli: Callable[..., CliProcess], tmp_path: Path, log_path: Path
) -> None:
    """R12.4、决策 D-11：连不上模型时说明网络错误，不自动重试，随后回到输入提示。"""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    process = start_cli(
        {
            "LIME_STAR_BASE_URL": f"http://127.0.0.1:{port}/v1",
            "LIME_STAR_API_KEY": FAKE_KEY,
            "LIME_STAR_MODEL": FAKE_MODEL,
        }
    )
    process.wait_for("stdout", PROMPT)
    process.send("问")
    process.wait_for("stderr", "回合出错：网络错误。\n")
    process.wait_for("stdout", PROMPT, count=2)
    process.send("/exit")
    assert process.finish() == 0
    [record] = read_log(log_path)
    assert record["status"] == "failed"
    assert record["error"] == {"kind": "network", "status_code": None, "detail": ""}


def test_request_log_of_a_real_session_has_one_record_per_request(
    start_cli: Callable[..., CliProcess],
    model_env: dict[str, str],
    fake_model: FakeModel,
    log_path: Path,
) -> None:
    """R3.1、R3.2-S1：两轮对话两条字段齐全的记录，可按会话和回合关联；日志里没有消息内容和密钥。"""
    marker = "UNIQUE-MARKER-九九九九"
    fake_model.reply("第一答")
    fake_model.reply("第二答")
    process = start_cli(model_env)
    process.wait_for("stdout", PROMPT)
    process.send(f"第一问 {marker}")
    process.wait_for("stdout", "第一答\n")
    process.wait_for("stdout", PROMPT, count=2)
    process.send("第二问")
    process.wait_for("stdout", "第二答\n")
    process.wait_for("stdout", PROMPT, count=3)
    process.send("/exit")
    assert process.finish() == 0
    records = read_log(log_path)
    assert len(records) == 2
    assert [list(record) for record in records] == [RECORD_KEYS, RECORD_KEYS]
    assert [record["status"] for record in records] == ["ok", "ok"]
    assert records[0]["session_id"] == records[1]["session_id"]
    assert records[0]["thread_id"] == records[1]["thread_id"]
    assert records[0]["turn_id"] != records[1]["turn_id"]
    assert records[0]["request_id"] != records[1]["request_id"]
    assert all(record["model"] == FAKE_MODEL for record in records)
    raw = log_path.read_text(encoding="utf-8")
    assert marker not in raw
    assert "第一答" not in raw
    assert FAKE_KEY not in raw


def test_step_limit_is_reported_on_the_terminal(
    start_cli: Callable[..., CliProcess],
    model_env: dict[str, str],
    fake_model: FakeModel,
    log_path: Path,
) -> None:
    """R12.3：模型每次都调用工具，20 次请求后回合结束，终端说明已达到步数上限，随后回到输入提示。"""
    for _ in range(20):
        fake_model.call(("no_such_tool", {}))
    process = start_cli(model_env)
    process.wait_for("stdout", PROMPT)
    process.send("一直调用工具")
    process.wait_for(
        "stdout",
        "回合结束：已达到步数上限（一个回合最多 20 次模型请求）。\n",
    )
    process.wait_for("stdout", PROMPT, count=2)
    process.send("/exit")
    assert process.finish() == 0
    assert process.output("stderr") == ""
    assert process.output("stdout").count("调用 no_such_tool {}") == 20
    assert process.output("stdout").count("结果出错：没有名为 no_such_tool 的工具。") == 19
    assert process.output("stdout").count("结果出错：没有执行：回合已达到步数上限。") == 1
    records = read_log(log_path)
    assert [record["status"] for record in records] == ["ok"] * 20
    assert len({record["turn_id"] for record in records}) == 1
    assert len({record["request_id"] for record in records}) == 20


def test_a_tool_call_is_shown_in_a_real_process(
    start_cli: Callable[..., CliProcess],
    model_env: dict[str, str],
    fake_model: FakeModel,
    tmp_path: Path,
) -> None:
    """R13.14-S1、R13.15-S1、R6.1-S1：真实进程里依次出现工具调用、结果摘要和最终回复。

    会话记录文件里的顺序与此一致。
    """
    (tmp_path / "notes.txt").write_text("甲\n乙\n", encoding="utf-8")
    fake_model.call(("read_file", {"path": "notes.txt"}))
    fake_model.reply("有两行")
    process = start_cli(model_env)
    process.wait_for("stdout", PROMPT)
    process.send("notes.txt 有几行")
    process.wait_for("stdout", "有两行\n")
    process.wait_for("stdout", PROMPT, count=2)
    process.send("/exit")
    assert process.finish() == 0
    assert process.output("stderr") == ""
    assert process.output("stdout").split(PROMPT)[1] == (
        '调用 read_file {"path": "notes.txt"}\n结果：读到 2 行\n有两行\n'
    )
    [file] = (tmp_path / ".lime-star" / "threads").glob("*.jsonl")
    types = [json.loads(line)["type"] for line in file.read_bytes().split(b"\n")[:-1]]
    assert types == [
        "turn_start",
        "user_message",
        "tool_call",
        "tool_result",
        "model_text",
        "turn_end",
    ]


ASK = "[y/n] "
REJECTION = "结果出错：用户拒绝了这次操作，没有执行。\n"
HELLO = "print('hello')\n"
WRITE_HELLO = json.dumps({"path": "hello.py", "content": HELLO})
TASK = "新建一个脚本 hello.py，打印 hello，然后运行它"


def recorded(workdir: Path) -> list[dict[str, object]]:
    """工作目录里那份会话记录的项，按写入顺序。"""
    raw = transcript_file(workdir).read_bytes()
    return [json.loads(line) for line in raw.split(b"\n")[:-1]]


def write_prompt(path: str, content: str, state: str = "新建文件") -> str:
    """期望的写文件批准提示。"""
    body = content if content.endswith("\n") else content + "\n"
    return (
        f"请求批准 write_file：写入 {path}（{state}）。要写入的内容：\n"
        f"{body}----- 内容结束，共 1 行 -----\n"
    )


def test_the_mvp_task_runs_in_a_real_process_with_two_approvals(
    start_cli: Callable[..., CliProcess],
    model_env: dict[str, str],
    fake_model: FakeModel,
    tmp_path: Path,
    log_path: Path,
) -> None:
    """R7.6、R7.7-S1、R7.8-S1：真实进程里写文件和执行命令各出现一次批准提示，输入 y 之后才执行；
    会话记录里调用、批准、结果依次落盘，命令输出在记录里（决策 D-08：终端只有一行摘要）。"""
    command = "python hello.py"
    fake_model.call(("write_file", WRITE_HELLO))
    fake_model.call(("run_command", {"command": command}))
    fake_model.reply("脚本运行成功，输出 hello。")
    process = start_cli(model_env)
    process.wait_for("stdout", PROMPT)
    process.send(TASK)
    process.wait_for("stdout", ASK)
    assert not (tmp_path / "hello.py").exists()  # 用户还没有回应：没有写
    process.send("y")
    process.wait_for("stdout", "已批准。\n")
    process.wait_for("stdout", ASK, count=2)
    process.send("y")
    process.wait_for("stdout", "已批准。\n", count=2)
    process.wait_for("stdout", PROMPT, count=2)
    process.send("/exit")
    assert process.finish() == 0
    assert process.output("stderr") == ""
    banner = process.output("stdout").split("\n", 1)[0] + "\n"
    command_prompt = f"请求批准 run_command：在工作目录里执行下面的命令：\n{command}\n"
    assert process.output("stdout") == (
        banner
        + PROMPT
        + f"调用 write_file {WRITE_HELLO}\n"
        + write_prompt("hello.py", HELLO)
        + "[y/n] 已批准。\n结果：已写入 hello.py，新建文件，1 行\n"
        + f"调用 run_command {json.dumps({'command': command})}\n"
        + command_prompt
        + "[y/n] 已批准。\n结果：退出码 0\n"
        + "脚本运行成功，输出 hello。\n"
        + PROMPT
    )
    assert (tmp_path / "hello.py").read_bytes() == HELLO.encode("utf-8")
    entries = recorded(tmp_path)
    assert [entry["type"] for entry in entries] == [
        "turn_start",
        "user_message",
        "tool_call",
        "approval",
        "tool_result",
        "tool_call",
        "approval",
        "tool_result",
        "model_text",
        "turn_end",
    ]
    approvals = [entry["decision"] for entry in entries if entry["type"] == "approval"]
    assert approvals == ["approved", "approved"]
    results = [entry["content"] for entry in entries if entry["type"] == "tool_result"]
    assert results == ["已写入 hello.py（新建文件，1 行）。", "退出码：0\nhello"]
    assert [record["status"] for record in read_log(log_path)] == ["ok"] * 3


def test_n_at_the_prompt_leaves_the_file_unwritten(
    start_cli: Callable[..., CliProcess],
    model_env: dict[str, str],
    fake_model: FakeModel,
    tmp_path: Path,
) -> None:
    """R7.9、R7.10-S1、R7.12、R7.13：真实进程里输入 n，文件没有被写入，终端和会话记录里都有拒绝，
    模型收到拒绝的结果后给出了最终回复。"""
    fake_model.call(("write_file", WRITE_HELLO))
    fake_model.reply("好的，我没有写入 hello.py。")
    process = start_cli(model_env)
    process.wait_for("stdout", PROMPT)
    process.send("新建 hello.py")
    process.wait_for("stdout", ASK)
    process.send("n")
    process.wait_for("stdout", PROMPT, count=2)
    process.send("/exit")
    assert process.finish() == 0
    assert not (tmp_path / "hello.py").exists()
    banner = process.output("stdout").split("\n", 1)[0] + "\n"
    assert process.output("stdout") == (
        banner
        + PROMPT
        + f"调用 write_file {WRITE_HELLO}\n"
        + write_prompt("hello.py", HELLO)
        + "[y/n] 已拒绝。\n"
        + REJECTION
        + "好的，我没有写入 hello.py。\n"
        + PROMPT
    )
    assert process.output("stderr") == ""
    entries = recorded(tmp_path)
    assert [(entry["type"], entry.get("decision")) for entry in entries] == [
        ("turn_start", None),
        ("user_message", None),
        ("tool_call", None),
        ("approval", "rejected"),
        ("tool_result", None),
        ("model_text", None),
        ("turn_end", None),
    ]
    assert entries[4]["content"] == "用户拒绝了这次操作，没有执行。"


def test_input_end_at_the_prompt_in_a_real_process_rejects(
    start_cli: Callable[..., CliProcess],
    model_env: dict[str, str],
    fake_model: FakeModel,
    tmp_path: Path,
) -> None:
    """R7.9、R13.13 的边界：批准提示处的输入结束按拒绝处理；
    随后在输入提示处读到输入结束，以 0 退出。"""
    fake_model.call(("write_file", WRITE_HELLO))
    fake_model.reply("没有写入。")
    process = start_cli(model_env)
    process.wait_for("stdout", PROMPT)
    process.send("新建 hello.py")
    process.wait_for("stdout", ASK)
    process.close_input()
    assert process.finish() == 0
    assert not (tmp_path / "hello.py").exists()
    assert process.output("stdout").endswith(
        "[y/n] 已拒绝。\n" + REJECTION + "没有写入。\n" + PROMPT
    )
    [approval] = [entry for entry in recorded(tmp_path) if entry["type"] == "approval"]
    assert approval["decision"] == "rejected"


def test_two_prompts_in_one_turn_are_decided_separately_in_a_real_process(
    start_cli: Callable[..., CliProcess],
    model_env: dict[str, str],
    fake_model: FakeModel,
    tmp_path: Path,
) -> None:
    """R7.11-S1：模型一次请求写两个文件，真实进程里出现两次批准提示；第一次拒绝，第二次仍然提示并执行。"""
    fake_model.call(
        ("write_file", '{"path": "a.txt", "content": "A"}'),
        ("write_file", '{"path": "b.txt", "content": "B"}'),
    )
    fake_model.reply("做完了")
    process = start_cli(model_env)
    process.wait_for("stdout", PROMPT)
    process.send("写两个文件")
    process.wait_for("stdout", ASK)
    process.send("n")
    process.wait_for("stdout", ASK, count=2)
    process.send("y")
    process.wait_for("stdout", PROMPT, count=2)
    process.send("/exit")
    assert process.finish() == 0
    assert not (tmp_path / "a.txt").exists()
    assert (tmp_path / "b.txt").read_bytes() == b"B"
    banner = process.output("stdout").split("\n", 1)[0] + "\n"
    assert process.output("stdout") == (
        banner
        + PROMPT
        + '调用 write_file {"path": "a.txt", "content": "A"}\n'
        + '调用 write_file {"path": "b.txt", "content": "B"}\n'
        + write_prompt("a.txt", "A")
        + "[y/n] 已拒绝。\n"
        + REJECTION
        + write_prompt("b.txt", "B")
        + "[y/n] 已批准。\n结果：已写入 b.txt，新建文件，1 行\n"
        + "做完了\n"
        + PROMPT
    )
    approvals = [entry["decision"] for entry in recorded(tmp_path) if entry["type"] == "approval"]
    assert approvals == ["rejected", "approved"]
