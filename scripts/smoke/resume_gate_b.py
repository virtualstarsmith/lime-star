"""Gate B 冒烟：会话恢复在真实的 lime-star 进程里发生（需求 R9、SC-3）。

    uv run python scripts/smoke/resume_gate_b.py           # 模型为回放夹具
    uv run python scripts/smoke/resume_gate_b.py --live    # 模型为真实接口，消耗额度

同一个工作目录里先后启动六个真实的 lime-star 进程，照 resume 场景的六段来：
新会话说一个名字；--resume 之后问这个名字；另开一个会话；--resume 恢复的是最后有活动的那个；
再开一个会话，模型请求写 hi.py，批准提示出现时把进程整棵强制结束，谁也不回应；
--resume，看到上一个回合没有完成、那次操作没有执行，然后接着问 hi.py 写好了没有。
外加两条用法：帮助里有 --resume；没有会话时 --resume 以 2 退出。

断言看的是事实源：会话记录文件（这里自己解析）、请求日志和磁盘。终端输出只用来核对说明和同步，
所以"进程输出是对的"不能冒充"事实源里是对的"。每项检查打印一行，退出码 0 表示全部通过。
回放时回放的是 tests/fixtures/provider/resume.json，它录自真实模型的一次运行；--live 用真实模型。
两种模式下的批准提示一律拒绝，要被结束的那一次不等它。
"""

import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))  # 共用 tests 里驱动真实进程、回放和场景的小工具

from tests.integration.fake_model import FAKE_KEY  # noqa: E402
from tests.integration.record_provider import NAME, SCENARIOS  # noqa: E402
from tests.integration.replay import (  # noqa: E402
    ReplayServer,
    load,
    recorded_bodies,
    runs,
    turns,
)
from tests.integration.smoke import (  # noqa: E402
    CLAIM,
    Checks,
    SmokeFailure,
    lime_star,
    wait_for_any,
)
from tests.integration.support import (  # noqa: E402
    CliProcess,
    child_env,
    kill_tree,
    lines_of,
    read_log,
    run_lime_star,
    transcript_files,
    wait_released,
)

from lime_star import __version__  # noqa: E402
from lime_star.cli.chat import ASK, PROMPT  # noqa: E402
from lime_star.model_provider import (  # noqa: E402
    API_KEY_VAR,
    BASE_URL_VAR,
    MODEL_VAR,
    ConfigError,
    load_config,
)
from lime_star.protocol import Decision  # noqa: E402
from lime_star.thread_store.turns import NOT_CLOSED, WAITING  # noqa: E402

WINDOWS = sys.platform == "win32"
Line = tuple[str, str, bool]
"""场景里的一个回合：用户的消息，对批准提示的做法，以及它是不是在等待批准时进程被结束。"""
Part = tuple[bool, list[int]]
"""相当于一个进程的一段：是不是 --resume，以及它跑场景里的哪几个回合。"""


@dataclass(frozen=True)
class Source:
    """冒烟用的模型来源：给子进程的三个配置变量、回合与分段的安排，以及回放服务（真实接口时没有）。"""

    env: dict[str, str]
    plan: list[Line]
    parts: list[Part]
    server: ReplayServer | None = None
    fixture: dict[str, Any] | None = None

    def describe(self) -> str:
        if self.fixture is None:
            return f"模型为真实接口（{self.env[MODEL_VAR]}）"
        return (
            f"模型为回放夹具（tests/fixtures/provider/resume.json，"
            f"{self.fixture['recorded']} 录制，模型 {self.fixture['model']}）"
        )


def source(live: bool, workdir: Path) -> Source:
    """回放时起本地的回放服务；--live 时读仓库根的模型配置。工作目录里放上场景要的文件。"""
    scenario = SCENARIOS["resume"]
    if live:
        config = load_config(os.environ, Path.cwd())
        for name, content in scenario.workdir.items():
            (workdir / name).write_text(content, encoding="utf-8", newline="\n")
        lines = [line for run in scenario.runs for line in run.turns]
        first, parts = 0, []
        for run in scenario.runs:
            parts.append((run.resume, list(range(first, first + len(run.turns)))))
            first += len(run.turns)
        return Source(
            env={
                BASE_URL_VAR: config.base_url,
                API_KEY_VAR: config.api_key,
                MODEL_VAR: config.model,
            },
            plan=[(line.message, line.policy, line.die) for line in lines],
            parts=parts,
        )
    fixture: dict[str, Any] = load("resume")
    for name, content in fixture["workdir"].items():
        (workdir / str(name)).write_text(str(content), encoding="utf-8", newline="\n")
    server = ReplayServer(fixture)
    return Source(
        env={
            BASE_URL_VAR: server.url + "/v1",
            API_KEY_VAR: FAKE_KEY,
            MODEL_VAR: str(fixture["model"]),
        },
        plan=[
            (str(turn["message"]), turn["policy"], turn["outcome"] == "interrupted")
            for turn in turns(fixture)
        ],
        parts=[(run.resume, list(run.turns)) for run in runs(fixture)],
        server=server,
        fixture=fixture,
    )


@dataclass
class Played:
    """一个进程跑完之后留下的东西。"""

    resume: bool
    killed: bool = False
    code: int = -1
    stdout: str = ""
    stderr: str = ""
    asked: list[Decision] = field(default_factory=list)
    """这个进程里交回的每一次批准决定。"""
    early_ask: bool = False
    """输入提示出现之前，终端上就已经有批准提示：恢复后自己请求了批准。"""
    requests: int = -1
    """输入提示第一次出现时，请求日志里已有多少条记录。"""
    requests_end: int = -1
    """这个进程结束时，请求日志里有多少条记录。"""
    cut: list[str] = field(default_factory=list)
    """被强制结束的那一刻，会话记录里各项的类型。"""


@dataclass(frozen=True)
class Story:
    """六个进程和两条用法跑完之后的全部证据。"""

    help_text: str
    lonely: tuple[int, str, str]
    empty: bool
    parts: list[Played]


def requests(workdir: Path) -> int:
    """到此刻为止，请求日志里有多少条记录。"""
    return len(read_log(workdir / ".lime-star" / "logs" / "requests.jsonl"))


def thread_of(workdir: Path, message: str) -> Path:
    """写着这条用户消息的那份会话记录。"""
    for path in transcript_files(workdir):
        if any(
            line.get("type") == "user_message" and line.get("content") == message
            for line in lines_of(path)
        ):
            return path
    raise SmokeFailure(f"没有找到写着这条消息的会话记录：{message!r}")


def play(
    process: CliProcess,
    resume: bool,
    indexes: Sequence[int],
    plan: Sequence[Line],
    workdir: Path,
    started: float,
) -> Played:
    """跑一段：等输入提示，逐个回合送消息；批准提示出现之后一律送 n。

    标了"被结束"的回合不等回应：批准提示一出现，就把进程整棵强制结束。
    """
    done = Played(resume)
    try:
        wait_for_any(process, [(PROMPT, 1)], started)
        done.early_ask = ASK in process.output("stdout")
        done.requests = requests(workdir)
        prompts = 1
        for index in indexes:
            message, _policy, die = plan[index]
            process.send(message)
            while True:
                hit = wait_for_any(
                    process, [(ASK, len(done.asked) + 1), (PROMPT, prompts + 1)], started
                )
                if hit == PROMPT:
                    prompts += 1
                    break
                if die:
                    # 调用先落盘，才轮到批准提示。记下此刻记录里的项，然后结束整棵进程树。
                    done.cut = [str(line["type"]) for line in lines_of(thread_of(workdir, message))]
                    kill_tree(process.process)
                    done.killed = True
                    return done
                process.send("n")
                done.asked.append("rejected")
                wait_for_any(process, [("已拒绝。\n", len(done.asked))], started)
        process.send("/exit")
        try:
            process.process.wait(timeout=60)
        except subprocess.TimeoutExpired:
            raise SmokeFailure("送出 /exit 之后进程没有退出。") from None
        done.code = process.finish(timeout=10)
    finally:
        # Windows 上 lime-star 是启动器，会话进程是它的子进程：没收尾就结束整棵进程树。
        if process.process.poll() is None:
            kill_tree(process.process)
        done.stdout, done.stderr = process.output("stdout"), process.output("stderr")
        done.requests_end = requests(workdir)
        process.close()
    return done


def stage(exe: Path, workdir: Path, origin: Source) -> Story:
    """两条用法，然后六段，每段一个真实的进程。"""
    started = time.monotonic()
    helped = run_lime_star(exe, ["--help"], workdir)
    lonely = run_lime_star(exe, ["--resume"], workdir)
    empty = not (workdir / ".lime-star").exists()
    parts = []
    for resume, indexes in origin.parts:
        args = ["--resume"] if resume else []
        parts.append(
            play(
                CliProcess(exe, workdir, child_env(origin.env), args),
                resume,
                indexes,
                origin.plan,
                workdir,
                started,
            )
        )
        if parts[-1].killed:
            # 被结束的进程握着那个会话的独占写入：等它放开，下一段才能恢复。
            wait_released(workdir, thread_of(workdir, origin.plan[indexes[0]][0]).stem)
    return Story(helped.stdout, (lonely.returncode, lonely.stdout, lonely.stderr), empty, parts)


def turns_of(path: Path) -> list[list[dict[str, Any]]]:
    """会话记录里的回合：每个回合是一个列表，从回合开始项到结局项。这里自己解析文件。"""
    result: list[list[dict[str, Any]]] = []
    for line in lines_of(path):
        if line.get("type") == "turn_start":
            result.append([])
        if result:
            result[-1].append(line)
    return result


def final_reply(path: Path, turn: int) -> str:
    """第 turn 个回合里最后一段模型文本：模型的最终回复。"""
    said = [
        str(line["content"])
        for line in turns_of(path)[turn - 1]
        if line.get("type") == "model_text"
    ]
    return said[-1] if said else ""


def check(checks: Checks, story: Story, origin: Source, workdir: Path) -> None:
    """对着会话记录、请求日志和磁盘逐项核对。"""
    banner = f"lime-star {__version__}  {workdir}\n"
    checks.that("帮助里有 --resume（R9.1-S3）", "--resume" in story.help_text)
    code, out, errors = story.lonely
    errors = errors.replace("\r\n", "\n")
    checks.that(
        "没有会话时 --resume 以 2 退出，标准错误说明没有可恢复的会话，标准输出为空（R9.1-S2）",
        code == 2 and out == "" and "没有可恢复的会话" in errors,
        f"退出码 {code}，标准错误 {errors[:120]!r}",
    )
    checks.that("没有会话时不建运行时目录", story.empty)
    [named, asked, second, again, cut, closed] = story.parts
    for number, part in enumerate(story.parts, start=1):
        if not part.killed:
            checks.that(
                f"第 {number} 个进程以 0 退出，标准错误没有输出",
                (part.code, part.stderr) == (0, ""),
                f"退出码 {part.code}，标准错误 {part.stderr[:200]!r}",
            )
    plan = origin.plan
    first = thread_of(workdir, plan[0][0])
    other = thread_of(workdir, plan[2][0])
    broken = thread_of(workdir, plan[4][0])

    # 恢复之后接着聊（R9.1、R9.2-S1、R9.5-S2）。
    reply = final_reply(first, 2)
    print(f"恢复后问名字的回答：{reply[:240]!r}")
    checks.that(
        "恢复：终端是横幅、一行说明、输入提示、回答、输入提示，没有重放之前的输出（R9.1、R9.5-S2）",
        asked.stdout
        == banner + f"已恢复会话 {first.stem}，已有 1 个回合。\n" + PROMPT + reply + "\n" + PROMPT,
        asked.stdout[-300:],
    )
    checks.that("恢复：模型的回答里有之前说过的名字（R9.2-S1）", NAME in reply, reply[:160])
    checks.that(
        "三个进程各写各的：工作目录下只有三份会话记录，恢复没有另起一份",
        len(transcript_files(workdir)) == 3
        and (len(turns_of(first)), len(turns_of(other))) == (2, 2),
    )
    records = read_log(workdir / ".lime-star" / "logs" / "requests.jsonl")
    of_first = [record for record in records if record["thread_id"] == first.stem]
    checks.that(
        "请求日志：恢复后的请求带新的会话标识和原来的线程标识",
        len({record["session_id"] for record in of_first}) == 2,
    )

    # 工作目录下有两个会话时，恢复最后有活动的那个（R9.1-S1）。
    checks.that(
        "两个会话之后 --resume 恢复的是最后有活动的那个（R9.1-S1）",
        again.stdout.startswith(banner + f"已恢复会话 {other.stem}，已有 1 个回合。\n" + PROMPT),
        again.stdout[:300],
    )

    # 批准提示出现时进程被强制结束（R9.3-S2、R9.4-S1）。
    checks.that(
        "被结束的进程：批准提示出现时进程被强制结束",
        cut.killed,
        "、".join(cut.cut) or "没有等到批准提示",
    )
    checks.that(
        "被结束的进程：记录里最后是一项工具调用，没有批准、没有结局",
        bool(cut.cut)
        and cut.cut[-1] == "tool_call"
        and not ({"approval", "turn_end"} & set(cut.cut)),
        "、".join(cut.cut),
    )
    reason = f"{NOT_CLOSED}，当时正在等待批准 write_file，这次操作没有执行"
    said = final_reply(broken, 2)
    print(f"恢复后问 hi.py 的回答：{said[:240]!r}")
    checks.that(
        "恢复：说明上一个回合没有完成，原因写明当时在等待批准、操作没有执行（R9.4-S1）",
        closed.stdout.startswith(
            banner
            + f"已恢复会话 {broken.stem}，已有 1 个回合。\n"
            + f"上一个回合没有完成：{reason}。\n"
            + PROMPT
        ),
        closed.stdout[:400],
    )
    checks.that(
        "恢复：没有续跑，没有请求批准，也没有再请求模型",
        (closed.early_ask, closed.requests) == (False, cut.requests_end),
        f"提示之前有批准提示：{closed.early_ask}；恢复的进程开始时请求日志有 "
        f"{closed.requests} 条，被结束的进程留下 {cut.requests_end} 条",
    )
    mended = turns_of(broken)[0][-2:]
    checks.that(
        "记录：中断的回合补上了“没有执行”的结果和中断结局",
        [line.get("type") for line in mended] == ["tool_result", "turn_end"]
        and mended[0].get("content") == WAITING
        and (mended[1].get("outcome"), mended[1].get("reason")) == ("interrupted", reason),
        "、".join(str(line.get("type")) for line in turns_of(broken)[0]),
    )
    checks.that("hi.py 自始至终没有被写", not (workdir / "hi.py").exists())
    checks.that(
        "接着问：模型没有把 hi.py 说成已写好（R14.1）",
        bool(said) and not CLAIM.search(said),
        said[:160],
    )

    fixture, server = origin.fixture, origin.server
    if fixture is not None and server is not None:
        sent = server.script.sent
        recorded = recorded_bodies(fixture)
        roles = [[message["role"] for message in body["messages"]] for body in sent]
        recorded_roles = [[message["role"] for message in body["messages"]] for body in recorded]
        checks.that("回放时请求的次数和角色的序列与录制时相同", roles == recorded_roles)
        checks.that(
            "回放：恢复后的第一个请求带上了恢复之前的问答",
            [message["content"] for message in sent[1]["messages"][1:]]
            == [plan[0][0], final_reply(first, 1), plan[1][0]],
        )
        checks.that(
            "回放：恢复后发给模型的历史里有那条“没有执行”的结果",
            any(
                message.get("role") == "tool" and message.get("content") == WAITING
                for message in sent[-1]["messages"]
            ),
        )
        if WINDOWS:
            same = [body["messages"][1:] for body in sent] == [
                body["messages"][1:] for body in recorded
            ]
            checks.that("回放时发给模型的内容与录制时逐项相同（系统指令除外）", same)
        expected = [decision for turn in turns(fixture) for decision in turn["decisions"]]
        checks.that(
            "交回的决定与录制时相同",
            [decision for part in story.parts for decision in part.asked] == expected,
        )
    key = origin.env[API_KEY_VAR]
    shown = "".join(part.stdout + part.stderr for part in story.parts)
    shown += story.help_text + "".join(story.lonely[1:])
    raw = "".join(path.read_text("utf-8") for path in transcript_files(workdir))
    checks.that("密钥不出现在终端输出和会话记录里（R4.3）", key not in shown + raw)


def main(argv: Sequence[str]) -> int:
    if argv not in ([], ["--live"]):
        print("用法：uv run python scripts/smoke/resume_gate_b.py [--live]")
        return 2
    checks = Checks()
    with tempfile.TemporaryDirectory(prefix="lime-star-smoke-resume-") as tmp:
        workdir = Path(tmp)
        try:
            origin = source(argv == ["--live"], workdir)
        except ConfigError as exc:
            print(f"读不到模型配置：{exc.message}")
            return 2
        print("模型来源：" + origin.describe())
        try:
            try:
                story = stage(lime_star(), workdir, origin)
            except SmokeFailure as exc:
                print(f"失败：冒烟没有跑完。{exc}")
                return 1
            check(checks, story, origin, workdir)
        finally:
            if origin.server is not None:
                origin.server.close()
    verdict = "通过" if checks.failed == 0 else "失败"
    print(f"冒烟{verdict}：{checks.passed} 项通过，{checks.failed} 项失败。{origin.describe()}。")
    return 1 if checks.failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
