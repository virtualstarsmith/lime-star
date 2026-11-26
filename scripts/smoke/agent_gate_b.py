"""Gate B 冒烟：MVP 主场景在一个真实的 lime-star 进程里完整发生（需求 SC-1、SC-2）。

    uv run python scripts/smoke/agent_gate_b.py           # 模型为回放夹具
    uv run python scripts/smoke/agent_gate_b.py --live    # 模型为真实接口，消耗额度

真实启动一个 lime-star 进程，经管道送入三个回合的任务：主场景（新建脚本、运行脚本、报告结果）、
换一个文件再试并在批准提示处拒绝、运行一条以退出码 1 结束的命令。每次出现批准提示，等它出现之后
才送 y 或 n；回放时回放的是 tests/fixtures/provider/mvp.json，它录自真实模型的一次会话。

断言看的是事实源：会话记录文件（经 thread_store 的读入函数）和磁盘。终端输出只用来核对批准提示，
所以"进程输出是对的"不能冒充"事实源里是对的"。每项检查打印一行，退出码 0 表示全部通过。
--live 只放行场景点名的操作（见 record_provider.pointed_out），别的一律拒绝。
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))  # 共用 tests 里驱动真实进程、回放和场景的小工具

from tests.integration.fake_model import FAKE_KEY  # noqa: E402
from tests.integration.record_provider import SCENARIOS, pointed_out, script_of  # noqa: E402
from tests.integration.replay import ReplayServer, load, recorded_bodies, turns  # noqa: E402
from tests.integration.support import (  # noqa: E402
    CliProcess,
    child_env,
    kill_tree,
    transcript_file,
)

from lime_star.cli.chat import ASK, PROMPT  # noqa: E402
from lime_star.model_provider import API_KEY_VAR, BASE_URL_VAR, MODEL_VAR, ConfigError, load_config  # noqa: E402
from lime_star.protocol import (  # noqa: E402
    Approval,
    Decision,
    Item,
    ModelText,
    Pending,
    ToolCall,
    ToolResult,
    TurnStart,
)
from lime_star.thread_store import read  # noqa: E402

WINDOWS = sys.platform == "win32"
DANGEROUS = ("write_file", "run_command")
REJECTED = "用户拒绝了这次操作，没有执行。"
CLAIM = re.compile(
    r"(已经?|成功)(?:为您|帮你)?(?:在\S{0,12}?)?(?:写入|创建|新建|保存)|(?:写入|创建|新建|保存)成功"
)
"""把操作说成已完成的说法，例如"已写入 hello.py""已在工作目录新建""创建成功"。"""
LIMIT = 300.0
"""整个冒烟最多等这么久；等不到某段输出按失败处理，不让脚本挂着。"""


class SmokeFailure(Exception):
    """冒烟跑不下去了：等不到要等的输出。消息里有当时的两路输出。"""


class Checks:
    """逐项检查，逐行打印；任何一项失败，最后的退出码就是 1。"""

    def __init__(self) -> None:
        self.failed = 0
        self.passed = 0

    def that(self, name: str, ok: bool, detail: str = "") -> bool:
        if ok:
            self.passed += 1
        else:
            self.failed += 1
        print(
            f"{'通过' if ok else '失败'}：{name}" + (f"  ← {detail}" if detail and not ok else "")
        )
        return ok


def lime_star() -> Path:
    """与运行本脚本的解释器装在同一个环境里的 lime-star 命令。"""
    exe = Path(sys.executable).with_name("lime-star.exe" if os.name == "nt" else "lime-star")
    if not exe.is_file():
        raise SmokeFailure(f"找不到 {exe}：先执行 uv sync，再用 uv run 运行")
    return exe


def wait_for_any(process: CliProcess, marks: Sequence[tuple[str, int]], started: float) -> str:
    """等标准输出里出现任意一个标记的第 n 处，返回那个标记。等的是输出本身，不是固定时长。"""
    while True:
        for text, count in marks:
            if process.output("stdout").count(text) >= count:
                return text
        if time.monotonic() - started > LIMIT:
            raise SmokeFailure(
                f"等待 {marks} 超过 {LIMIT:.0f} 秒。"
                f"stdout={process.output('stdout')[-800:]!r}"
                f" stderr={process.output('stderr')[-400:]!r}"
            )
        time.sleep(0.01)


@dataclass(frozen=True)
class Source:
    """冒烟用的模型来源：给子进程的三个配置变量、逐个回合的消息与做法，以及回放服务（真实接口时没有）。"""

    env: dict[str, str]
    plan: list[tuple[str, Decision]]
    server: ReplayServer | None = None
    fixture: dict[str, Any] | None = None

    def describe(self) -> str:
        if self.fixture is None:
            return f"模型为真实接口（{self.env[MODEL_VAR]}）"
        return (
            f"模型为回放夹具（tests/fixtures/provider/mvp.json，"
            f"{self.fixture['recorded']} 录制，模型 {self.fixture['model']}）"
        )


def source(live: bool, workdir: Path) -> Source:
    """回放时起本地的回放服务；--live 时读仓库根的模型配置。工作目录里放上场景要的文件。"""
    scenario = SCENARIOS["mvp"]
    if live:
        config = load_config(os.environ, Path.cwd())
        for name, content in scenario.workdir.items():
            (workdir / name).write_text(content, encoding="utf-8", newline="\n")
        return Source(
            env={
                BASE_URL_VAR: config.base_url,
                API_KEY_VAR: config.api_key,
                MODEL_VAR: config.model,
            },
            plan=[(line.message, line.policy) for line in scenario.turns],
        )
    fixture: dict[str, Any] = load("mvp")
    for name, content in fixture["workdir"].items():
        (workdir / str(name)).write_text(str(content), encoding="utf-8", newline="\n")
    server = ReplayServer(fixture)
    return Source(
        env={
            BASE_URL_VAR: server.url + "/v1",
            API_KEY_VAR: FAKE_KEY,
            MODEL_VAR: str(fixture["model"]),
        },
        plan=[(str(turn["message"]), turn["policy"]) for turn in turns(fixture)],
        server=server,
        fixture=fixture,
    )


def decide(index: int, policy: Decision, workdir: Path) -> Decision:
    """按场景的做法交回决定；要批准的回合里也只放行场景点名的操作。

    正在等待的调用是会话记录里最后一条工具调用：它先落盘，才轮到批准提示。
    """
    if policy != "approved":
        return "rejected"
    entries = read(transcript_file(workdir))
    call = [entry.item for entry in entries if isinstance(entry.item, ToolCall)][-1]
    pending = Pending(call.call_id, call.name, call.arguments, "")
    return "approved" if pointed_out(index, pending) else "rejected"


def drive(
    process: CliProcess, plan: Sequence[tuple[str, Decision]], workdir: Path
) -> list[Decision]:
    """逐个回合送入消息；每次批准提示出现之后才送 y 或 n。返回交回的决定。"""
    started = time.monotonic()
    wait_for_any(process, [(PROMPT, 1)], started)
    prompts = 0
    shown = {"approved": 0, "rejected": 0}
    decisions: list[Decision] = []
    for index, (message, policy) in enumerate(plan):
        process.send(message)
        while True:
            hit = wait_for_any(process, [(ASK, prompts + 1), (PROMPT, index + 2)], started)
            if hit == PROMPT:
                break
            prompts += 1
            decision = decide(index, policy, workdir)
            decisions.append(decision)
            process.send("y" if decision == "approved" else "n")
            shown[decision] += 1
            echo = "已批准。\n" if decision == "approved" else "已拒绝。\n"
            wait_for_any(process, [(echo, shown[decision])], started)
    return decisions


@dataclass(frozen=True)
class Run:
    """一次冒烟跑完后的全部证据。"""

    plan: Sequence[tuple[str, Decision]]
    decisions: Sequence[Decision]
    code: int
    stdout: str
    stderr: str
    workdir: Path
    env: dict[str, str]
    source: Source


Trio = tuple[ToolCall, Approval, ToolResult]


def trios(items: Sequence[Item]) -> list[Trio]:
    """会话记录里每个危险调用和紧跟它的批准项、结果；缺了哪一样，它就不在返回里。"""
    found: list[Trio] = []
    for index, item in enumerate(items):
        if not (isinstance(item, ToolCall) and item.name in DANGEROUS) or index + 2 >= len(items):
            continue
        approval, result = items[index + 1], items[index + 2]
        if (
            isinstance(approval, Approval)
            and isinstance(result, ToolResult)
            and approval.call_id == result.call_id == item.call_id
        ):
            found.append((item, approval, result))
    return found


def arguments_of(call: ToolCall) -> dict[str, Any]:
    arguments: dict[str, Any] = json.loads(call.arguments)
    return arguments


def check(checks: Checks, ran: Run) -> None:
    """对着会话记录和磁盘逐项核对。"""
    entries = list(read(transcript_file(ran.workdir)))
    items = [entry.item for entry in entries]
    kinds = [item.kind for item in items]
    checks.that("进程以 0 退出", ran.code == 0, f"退出码 {ran.code}")
    checks.that("标准错误没有输出", ran.stderr == "", ran.stderr[:300])
    started = kinds.count("turn_start")
    checks.that(
        "每个回合都有开始和结局",
        started == len(ran.plan) == kinds.count("turn_end"),
        f"开始 {started} 个，结局 {kinds.count('turn_end')} 个",
    )
    # AGENTS.md 的审批硬规则：危险操作必须先有批准项，才有结果。
    triples = trios(items)
    complete = {call.call_id for call, _, _ in triples}
    loose = [
        f"{item.name} {item.arguments[:60]}"
        for item in items
        if isinstance(item, ToolCall) and item.name in DANGEROUS and item.call_id not in complete
    ]
    checks.that(
        f"{len(triples)} 次危险调用，每一次都先有批准项、后有结果",
        bool(triples) and not loose,
        "没有批准项或者没有结果：" + "；".join(loose),
    )

    def writes(path: str) -> list[Trio]:
        return [
            t for t in triples if t[0].name == "write_file" and arguments_of(t[0])["path"] == path
        ]

    def runs(script: str) -> list[Trio]:
        return [
            t
            for t in triples
            if t[0].name == "run_command" and script_of(arguments_of(t[0])["command"]) == script
        ]

    hello, bye = writes("hello.py"), writes("bye.py")
    run_hello, run_fail = runs("hello.py"), runs("fail.py")
    granted = (
        bool(hello)
        and hello[0][1].decision == "approved"
        and hello[0][2].content.startswith("已写入 hello.py")
    )
    checks.that("主场景：写 hello.py 经批准后执行，结果说已写入", granted)
    ran_well = (
        bool(run_hello)
        and run_hello[0][1].decision == "approved"
        and run_hello[0][2].content.startswith("退出码：0")
        and "hello" in run_hello[0][2].content
    )
    checks.that("主场景：运行 hello.py 经批准后执行，命令输出 hello 在会话记录里", ran_well)
    if hello:
        content = str(arguments_of(hello[0][0])["content"])
        target = ran.workdir / "hello.py"
        checks.that(
            "磁盘：hello.py 的内容与批准时显示的内容逐字节相同",
            target.is_file() and target.read_bytes() == content.encode("utf-8"),
        )
    if (ran.workdir / "hello.py").is_file():
        again = subprocess.run(
            [sys.executable, "hello.py"],
            cwd=ran.workdir,
            capture_output=True,
            timeout=60,
            check=False,
        )
        checks.that(
            "磁盘：现在运行 hello.py，它打印 hello",
            again.returncode == 0 and "hello" in again.stdout.decode("utf-8", "replace"),
            again.stderr.decode("utf-8", "replace")[:200],
        )
    checks.that(
        "拒绝：写 bye.py 被拒绝，没有执行，拒绝的结果交回了模型（R7.10、R7.13）",
        bool(bye)
        and bye[0][1].decision == "rejected"
        and bye[0][2].content == REJECTED
        and not (ran.workdir / "bye.py").exists(),
    )
    checks.that(
        "失败的命令：运行 fail.py 的结果以退出码 1 交回模型",
        bool(run_fail)
        and run_fail[0][1].decision == "approved"
        and run_fail[0][2].content.startswith("退出码：1"),
    )
    # 批准提示（R7.7、R7.8）：终端上显示的就是这次调用的路径与全部内容，或者原样的命令。
    for call, _, _ in triples:
        if call.name == "run_command":
            command = str(arguments_of(call)["command"])
            checks.that(
                "批准提示里的命令与请求的逐字相同（R7.8-S1）",
                f"请求批准 run_command：在工作目录里执行下面的命令：\n{command}\n" in ran.stdout,
                command[:80],
            )
        else:
            arguments = arguments_of(call)
            shown = re.search(
                rf"请求批准 write_file：写入 {re.escape(str(arguments['path']))}"
                rf"（新建文件|覆盖已有文件）。要写入的内容：\n{re.escape(str(arguments['content']))}",
                ran.stdout,
            )
            checks.that(
                f"写 {arguments['path']} 的批准提示显示路径、新建还是覆盖和全部内容（R7.7）",
                shown is not None,
            )
    approved = [trio for trio in triples if trio[1].decision == "approved"]
    rejected = [trio for trio in triples if trio[1].decision == "rejected"]
    checks.that(
        "终端上每次批准都显示“已批准。”",
        ran.stdout.count("[y/n] 已批准。\n")
        == len(approved)
        == list(ran.decisions).count("approved"),
    )
    checks.that(
        "终端上每次拒绝都显示“已拒绝。”",
        ran.stdout.count("[y/n] 已拒绝。\n")
        == len(rejected)
        == list(ran.decisions).count("rejected"),
    )
    # R14：最终回复的说法与会话记录一致。把每个回合的项和最终回复打印出来，作为证据。
    turns_items: list[list[Item]] = []
    for item in items:
        if isinstance(item, TurnStart):
            turns_items.append([])
        if turns_items:
            turns_items[-1].append(item)
    finals: list[str] = []
    for number in range(1, len(ran.plan) + 1):
        turn_items = turns_items[number - 1] if number <= len(turns_items) else []
        replies = [item.content for item in turn_items if isinstance(item, ModelText)]
        finals.append(replies[-1] if replies else "")
        print(f"回合 {number} 的项：{' '.join(item.kind for item in turn_items)}")
        print(f"回合 {number} 的最终回复：{finals[-1][:240]!r}")
    checks.that("每个回合都有最终回复", len(turns_items) == len(ran.plan) and all(finals))
    if len(finals) >= 3 and all(finals[:3]):
        checks.that(
            "被拒绝的写入没有被说成已完成（R14.1-S1）",
            not CLAIM.search(finals[1]),
            finals[1][:160],
        )
        checks.that(
            "以退出码 1 结束的命令被指出失败（R14.2-S1）",
            "失败" in finals[2] or ("退出码" in finals[2] and "1" in finals[2]),
            finals[2][:160],
        )
    key = ran.env[API_KEY_VAR]
    raw = transcript_file(ran.workdir).read_text("utf-8")
    checks.that(
        "密钥不出现在终端输出和会话记录里（R4.3）", key not in ran.stdout + ran.stderr + raw
    )
    fixture, server = ran.source.fixture, ran.source.server
    if fixture is not None and server is not None:
        recorded = recorded_bodies(fixture)
        sent = server.script.sent
        roles = [[message["role"] for message in body["messages"]] for body in sent]
        recorded_roles = [[message["role"] for message in body["messages"]] for body in recorded]
        checks.that("回放时请求的次数和角色的序列与录制时相同", roles == recorded_roles)
        if WINDOWS:
            same = [body["messages"][1:] for body in sent] == [
                body["messages"][1:] for body in recorded
            ]
            checks.that("回放时发给模型的内容与录制时逐项相同（系统指令除外）", same)
        expected = [decision for turn in turns(fixture) for decision in turn["decisions"]]
        checks.that("交回的决定与录制时相同", list(ran.decisions) == expected)


def main(argv: Sequence[str]) -> int:
    if argv not in ([], ["--live"]):
        print("用法：uv run python scripts/smoke/agent_gate_b.py [--live]")
        return 2
    checks = Checks()
    with tempfile.TemporaryDirectory(prefix="lime-star-smoke-") as tmp:
        workdir = Path(tmp)
        try:
            origin = source(argv == ["--live"], workdir)
        except ConfigError as exc:
            print(f"读不到模型配置：{exc.message}")
            return 2
        print("模型来源：" + origin.describe())
        try:
            process = CliProcess(lime_star(), workdir, child_env(origin.env))
            try:
                decisions = drive(process, origin.plan, workdir)
                process.send("/exit")
                try:
                    process.process.wait(timeout=60)
                except subprocess.TimeoutExpired:
                    raise SmokeFailure("送出 /exit 之后进程没有退出。") from None
                code = process.finish(timeout=10)
            finally:
                # Windows 上 lime-star 是启动器，会话进程是它的子进程：没收尾就结束整棵进程树。
                if process.process.poll() is None:
                    kill_tree(process.process)
                process.close()
            ran = Run(
                plan=origin.plan,
                decisions=decisions,
                code=code,
                stdout=process.output("stdout"),
                stderr=process.output("stderr"),
                workdir=workdir,
                env=origin.env,
                source=origin,
            )
        except SmokeFailure as exc:
            print(f"失败：冒烟没有跑完。{exc}")
            return 1
        finally:
            if origin.server is not None:
                origin.server.close()
        check(checks, ran)
    verdict = "通过" if checks.failed == 0 else "失败"
    print(f"冒烟{verdict}：{checks.passed} 项通过，{checks.failed} 项失败。{origin.describe()}。")
    return 1 if checks.failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
