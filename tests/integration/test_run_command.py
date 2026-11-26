"""run_command 真正执行命令：退出码、输出、环境、超时、截断、Ctrl+C、进程树与批准前的等待。

证据等级：工具经注册表执行，命令是真的在子进程里跑，不带模型。经 app 回合入口被模型调用的场景在
test_approval.py；真实进程和真实控制台里的在 test_cli_process.py、test_cli_console.py。
覆盖 R7.3 到 R7.6、R7.8、R8.4-S1、R12.5-S1。
命令只用 PATH 上的 python 和 uv，Windows 和 Linux 都能跑。
"""

import json
import sys
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from lime_star.protocol import Approver, Halted, Pending, ToolCall, ToolResult, ToolSet
from lime_star.tool_runtime import REJECTED, Registry, run_command
from tests.integration.support import SLEEPER, alive, wait_until

WINDOWS = sys.platform == "win32"
POSIX_ONLY = pytest.mark.skipif(WINDOWS, reason="只在其他平台上由 /bin/sh 解释")
WINDOWS_ONLY = pytest.mark.skipif(not WINDOWS, reason="只在 Windows 上由 Windows PowerShell 解释")

NOTES: list[str] = []
"""批准来源收到过的说明。"""


def take_note(pending: Pending) -> bool:
    """批准来源的替身：记下说明，批准。"""
    NOTES.append(pending.note)
    return True


def refuse(_pending: Pending) -> bool:
    return False


def py(code: str) -> str:
    """一条跨平台的命令：用 PATH 上的 python 执行一段只用单引号的代码。"""
    return f'python -c "{code}"'


def call(command: str) -> ToolCall:
    arguments = json.dumps({"command": command}, ensure_ascii=False)
    return ToolCall(call_id="c1", name="run_command", arguments=arguments)


def failed(reason: str) -> ToolResult:
    """出错的工具结果：同一句说明既交给模型，也是给终端看的摘要。"""
    return ToolResult("c1", reason, error=True, summary=reason)


def tools_for(workdir: Path, approve: Approver | None, timeout: float = 120.0) -> ToolSet:
    registry = Registry([run_command(workdir, timeout)])
    return registry.approved_by(approve) if approve is not None else registry


def run(workdir: Path, command: str, *, timeout: float = 120.0) -> ToolResult:
    """经注册表执行一条命令，默认有人批准；和模型调用它时走的是同一条路。"""
    NOTES.clear()
    return tools_for(workdir, take_note, timeout).execute(call(command))


LAUNCHER = """\
import subprocess
import sys
import time
from pathlib import Path

subprocess.Popen([sys.executable, "sleeper.py"])
while not Path("pids.txt").exists():
    time.sleep(0.05)
print("launcher done", flush=True)
"""
# 留下一个后台进程就退出的命令：后台进程占着标准输出。用注释，不给它拼字符串。


def sleepers(workdir: Path) -> tuple[int, int]:
    """sleeper.py 写下的两个进程号：它自己的和它派生的。"""
    parent, child = map(int, (workdir / "pids.txt").read_text().split())
    return parent, child


def test_a_command_that_prints_and_exits_zero(tmp_path: Path) -> None:
    """R7.3-S1：命令向标准输出打印一行并以 0 退出，结果里有退出码 0 和这一行。"""
    result = run(tmp_path, py("print('hello 世界')"))
    assert result == ToolResult("c1", "退出码：0\nhello 世界", summary="退出码 0")


def test_a_command_that_fails_on_stderr(tmp_path: Path) -> None:
    """R7.3-S2：命令以 1 退出并向标准错误打印信息，结果里有退出码 1 和这条信息。"""
    result = run(tmp_path, py("import sys; sys.stderr.write('boom'); sys.exit(1)"))
    assert result == ToolResult("c1", "退出码：1\n（以下是标准错误）\nboom", True, "退出码 1")


def test_the_exit_code_of_a_native_command_is_passed_through(tmp_path: Path) -> None:
    """R7.3：原生命令的退出码原样带回，不被解释器压成 1；成功的命令是 0。"""
    assert run(tmp_path, py("raise SystemExit(3)")).content == "退出码：3"
    assert run(tmp_path, py("raise SystemExit(0)")).content == "退出码：0"


def test_the_command_inherits_the_environment(tmp_path: Path) -> None:
    """R7.3-S3：命令继承 lime-star 进程的环境变量，PATH 上的 uv 找得到。"""
    result = run(tmp_path, "uv --version")
    assert (result.error, result.summary) == (False, "退出码 0")
    assert result.content.splitlines()[1].startswith("uv ")


def test_the_command_runs_in_the_workdir(tmp_path: Path) -> None:
    """R7.3：命令在工作目录里执行。"""
    result = run(tmp_path, py("import os; print(os.getcwd())"))
    assert result.error is False
    assert Path(result.content.split("\n")[1]).samefile(tmp_path)


def test_the_command_cannot_read_stdin(tmp_path: Path) -> None:
    """命令的标准输入是空的：它读不到留给用户的输入。"""
    result = run(tmp_path, py("import sys; print(repr(sys.stdin.read()))"))
    assert result.content == "退出码：0\n''"


def test_a_command_that_runs_too_long_is_terminated_with_its_output(tmp_path: Path) -> None:
    """R7.4-S1：命令一直运行，到时限时它和它的子进程都被终止，结果标明超时并带上已有的输出。"""
    (tmp_path / "sleeper.py").write_text(SLEEPER, encoding="utf-8")
    started = time.monotonic()
    result = run(tmp_path, "python sleeper.py", timeout=2.0)
    assert time.monotonic() - started < 20
    assert result == ToolResult(
        "c1",
        "命令超过 2 秒，已被终止（超时）。截至那时已有的输出如下。\nstarted",
        True,
        "超过 2 秒，已终止",
    )
    parent, child = sleepers(tmp_path)
    wait_until(lambda: not (alive(parent) or alive(child)))


def test_output_is_cut_to_the_last_10000_characters(tmp_path: Path) -> None:
    """R7.5-S1：命令打印 30000 个字符，结果只留最后 10000 个，前面标明截掉了 20000 个。"""
    result = run(tmp_path, py("print('x' * 30000, end='')"))
    assert result.content == (
        "退出码：0\n（命令输出共 30000 个字符，只保留最后 10000 个，截掉了前面的 20000 个。）\n"
        + "x" * 10000
    )


def test_output_that_is_not_utf8_does_not_break_the_result(tmp_path: Path) -> None:
    """解不开的字节用替换字符，不出异常，也不丢掉前面解得开的部分。"""
    result = run(tmp_path, py("import sys; sys.stdout.buffer.write(b'ok \\xff\\xfe')"))
    assert (result.error, result.content[:9]) == (False, "退出码：0\nok ")
    assert "\ufffd" in result.content


def test_a_command_is_not_started_until_it_is_approved(tmp_path: Path) -> None:
    """R7.6-S1：用户还没有回应时命令没有运行；被拒绝和没有人可问时都不运行（决策 D-19）。"""
    marker = py("from pathlib import Path; Path('marker.txt').write_text('x', encoding='utf-8')")
    touched = tmp_path / "marker.txt"

    def looking(_pending: Pending) -> bool:
        assert not touched.exists()
        return False

    assert tools_for(tmp_path, looking).execute(call(marker)) == failed(REJECTED)
    assert tools_for(tmp_path, None).execute(call(marker)) == failed(REJECTED)
    assert not touched.exists()


def test_the_prompt_shows_the_command_verbatim(tmp_path: Path) -> None:
    """R7.8-S1：批准提示里的命令与请求的逐字相同，包括引号、空格、多行和中文。"""
    command = py("print('你好')") + ("\nWrite-Output '第二行'" if WINDOWS else "\necho '第二行'")
    assert run(tmp_path, command).error is False
    assert NOTES == [f"请求批准 run_command：在工作目录里执行下面的命令：\n{command}"]


def test_a_command_that_reaches_outside_the_workdir_still_asks(tmp_path: Path) -> None:
    """R8.4-S1：命令里出现工作目录之外的路径，仍然进入批准提示，由用户决定（决策 D-22）。"""
    (tmp_path / "outside").mkdir()
    work = tmp_path / "work"
    work.mkdir()
    command = py("from pathlib import Path; Path('../outside/touched.txt').write_text('x')")
    assert run(work, command).summary == "退出码 0"
    assert (tmp_path / "outside" / "touched.txt").exists()
    assert NOTES == [f"请求批准 run_command：在工作目录里执行下面的命令：\n{command}"]


def test_ctrl_c_while_a_command_runs_terminates_it_and_keeps_its_output(
    tmp_path: Path, ctrl_c: Callable[[Callable[[], bool]], None]
) -> None:
    """R12.5-S1：命令运行中按 Ctrl+C，命令进程及其子进程都结束，已经产生的输出带在结果里。"""
    (tmp_path / "sleeper.py").write_text(SLEEPER, encoding="utf-8")
    ctrl_c(lambda: (tmp_path / "pids.txt").exists())
    with pytest.raises(Halted) as caught:
        run(tmp_path, "python sleeper.py")
    assert (caught.value.text, caught.value.summary) == (
        "用户按 Ctrl+C 取消了回合，命令已被终止。截至那时已有的输出如下。\nstarted",
        "已取消，命令已终止",
    )
    parent, child = sleepers(tmp_path)
    wait_until(lambda: not (alive(parent) or alive(child)))


def test_a_command_that_leaves_a_background_process_does_not_hold_up_the_result(
    tmp_path: Path,
) -> None:
    """命令结束后它留下的后台进程一并结束，不会让结果等到超时，也不会活过这次调用。"""
    (tmp_path / "sleeper.py").write_text(SLEEPER, encoding="utf-8")
    (tmp_path / "launcher.py").write_text(LAUNCHER, encoding="utf-8")
    started = time.monotonic()
    result = run(tmp_path, "python launcher.py", timeout=15.0)
    assert time.monotonic() - started < 15
    # 后台进程继承了标准输出，它先打印的那一行也在结果里。
    assert result == ToolResult("c1", "退出码：0\nstarted\nlauncher done", summary="退出码 0")
    parent, child = sleepers(tmp_path)
    wait_until(lambda: not (alive(parent) or alive(child)))


@WINDOWS_ONLY
def test_a_powershell_error_is_plain_text_with_exit_code_one(tmp_path: Path) -> None:
    """Windows PowerShell 自己报的错是纯文本，退出码是 1，不是给程序看的 CLIXML。"""
    result = run(tmp_path, "throw 'boom'")
    assert (result.error, result.summary) == (True, "退出码 1")
    assert result.content.startswith("退出码：1\n（以下是标准错误）\nboom")
    assert "CLIXML" not in result.content


@WINDOWS_ONLY
def test_a_failing_cmdlet_after_a_successful_native_command_fails_with_one(tmp_path: Path) -> None:
    """最后一条语句失败时，前面原生命令留下的 0 不能把退出码带成 0。"""
    assert run(tmp_path, "cmd /c exit 0; Get-Item nope").content.startswith("退出码：1\n")
    assert run(tmp_path, "Get-Item nope").summary == "退出码 1"


@WINDOWS_ONLY
def test_quotes_variables_and_chinese_pass_through_to_powershell(tmp_path: Path) -> None:
    """命令当成一个参数交给 -Command：引号、美元符号、多行和中文都原样到达。"""
    assert (
        run(tmp_path, "Write-Output 'a \"b\" c 中文 $HOME'").content
        == '退出码：0\na "b" c 中文 $HOME'
    )
    assert run(tmp_path, "Write-Output one\nWrite-Output two").content == "退出码：0\none\ntwo"
    assert run(tmp_path, "Write-Output bye; exit 7").content == "退出码：7\nbye"


@POSIX_ONLY
def test_the_shell_redirects_stderr_and_passes_the_exit_code(tmp_path: Path) -> None:
    """其他平台上命令由 /bin/sh 解释：重定向和 exit 照 shell 的规矩。"""
    result = run(tmp_path, "echo out; echo boom >&2; exit 3")
    assert result == ToolResult("c1", "退出码：3\nout\n（以下是标准错误）\nboom", True, "退出码 3")
