"""从真实模型录制回放夹具（需求 R11.1）。只在需要新夹具时手动运行：

    uv run python -m tests.integration.record_provider <场景名>

它会消耗真实接口的额度。配置经产品自己的 load_config 读取；密钥只用于这些请求，
不写进夹具，也不打印。一个场景是一段固定的对话：工作目录里先放好的文件，和若干个回合。
录制时，一个回合里的每次批准请求都按同一种做法回应（全部批准，或者全部拒绝）。
场景见 SCENARIOS，录成的夹具是 tests/fixtures/provider/<场景名>.json。
"""

import hashlib
import json
import os
import re
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx2
from openai import OpenAI

from lime_star.app import Session, open_session
from lime_star.model_provider import API_KEY_VAR, BASE_URL_VAR, MODEL_VAR, ModelConfig, load_config
from lime_star.model_provider.prompt import SYSTEM_INSTRUCTION
from lime_star.protocol import Decision, Pending
from tests.integration.replay import FIXTURES


@dataclass(frozen=True)
class Line:
    """录制里的一个回合：用户的消息，以及对这个回合里每次批准请求的做法。"""

    message: str
    policy: Decision


@dataclass(frozen=True)
class Scenario:
    """一个场景：工作目录里先放好的文件，和按顺序录制的回合。"""

    workdir: dict[str, str]
    turns: tuple[Line, ...]


GENERATED = "@generated 由 tests/integration/record_provider.py 录制，不要手改；要更新就重新录制。"
"""夹具的第一项：告诉行数门禁和读它的人，这是录下来的数据。"""
NOTES = "第一行：lime-star\n第二行：会话记录\n第三行：回放夹具\n"
FAIL = """\
import sys

print("脚本开始")
print("boom：这一步失败了", file=sys.stderr)
sys.exit(1)
"""

SCENARIOS: dict[str, Scenario] = {
    "read_file": Scenario(
        workdir={"notes.txt": NOTES},
        turns=(Line("请读取 notes.txt，告诉我它一共有几行。", "approved"),),
    ),
    # MVP 主场景，加上拒绝一次，加上一条以退出码 1 结束的命令（R14.1-S1、R14.2-S1）。
    "mvp": Scenario(
        workdir={"fail.py": FAIL},
        turns=(
            Line("新建一个脚本 hello.py，打印 hello，然后运行它，把结果告诉我。", "approved"),
            Line("再新建一个脚本 bye.py，打印 bye，然后运行它，把结果告诉我。", "rejected"),
            Line("运行 fail.py，把结果告诉我。", "approved"),
        ),
    ),
}


RUNNABLE: dict[int, dict[str, set[str]]] = {
    0: {"write_file": {"hello.py"}, "run_command": {"hello.py"}},  # 主场景：写 hello.py，运行它
    2: {"run_command": {"fail.py"}},  # 运行一条以退出码 1 结束的命令
}
"""mvp 场景里每个回合点名的操作（工具，以及它作用的那个脚本）。第二个回合什么都不放行。"""

_SCRIPT = re.compile(r"^(?:python3?|python\.exe|py|uv run python)\s+\.?[\\/]?(\S+\.py)$")
"""点名的命令只有一种形状：用 python 运行工作目录里的一个脚本。"""


def script_of(command: str) -> str:
    """命令是不是"用 python 运行工作目录里的一个脚本"；是的话返回脚本名，否则返回空串。"""
    found = _SCRIPT.match(command)
    return found[1] if found else ""


def pointed_out(index: int, pending: Pending) -> bool:
    """这次等待批准的操作是不是 mvp 场景第 index 个回合点名的。

    真实模型面前只放行点名的操作，别的一律拒绝；回放用不到它，录下的响应里只有点名的操作。
    """
    allowed = RUNNABLE.get(index, {})
    arguments = json.loads(pending.arguments)
    if pending.name == "write_file":
        target = str(arguments.get("path", ""))
    else:
        target = script_of(str(arguments.get("command", "")))
    return target in allowed.get(pending.name, set())


def main(name: str) -> int:
    scenario = SCENARIOS[name]
    exchanges: list[dict[str, Any]] = []

    def on_response(response: httpx2.Response) -> None:
        response.read()
        exchanges.append(
            {
                "request": {
                    "path": response.request.url.path,
                    "body": json.loads(response.request.content),
                },
                "response": {"status": response.status_code, "body": response.json()},
            }
        )

    try:
        config = load_config(os.environ, Path.cwd())
    except Exception as exc:
        print(f"读不到模型配置（{type(exc).__name__}）：")
        print("在仓库根配置 .env，或者设置三个环境变量。")
        return 2
    with tempfile.TemporaryDirectory(prefix="lime-star-record-") as tmp:
        workdir = Path(tmp)
        for relative, content in scenario.workdir.items():
            path = workdir / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
        try:
            with _recording(config, on_response) as client:
                session = open_session(
                    env={
                        BASE_URL_VAR: config.base_url,
                        API_KEY_VAR: config.api_key,
                        MODEL_VAR: config.model,
                    },
                    workdir=workdir,
                    client=client,
                )
                recorded: list[dict[str, Any]] = []
                for index, line in enumerate(scenario.turns):
                    first = len(exchanges)
                    turn = _turn(session, line, index)
                    turn["exchanges"] = exchanges[first:]
                    recorded.append(turn)
            left = sorted(path.name for path in workdir.iterdir() if path.name != ".lime-star")
        except Exception as exc:
            # 异常文本可能带着请求头，所以只写异常类名。
            print(f"录制没有完成（{type(exc).__name__}）。")
            return 1
        print(f"录制结束时工作目录里的文件：{left}")
        text = _fixture_text(config, name, tmp, scenario, recorded)
    if text is None:
        return 1
    FIXTURES.mkdir(parents=True, exist_ok=True)
    target = FIXTURES / f"{name}.json"
    target.write_text(text, encoding="utf-8", newline="\n")
    done = [turn["outcome"] == "done" for turn in recorded]
    print(f"模型：{config.model}。回合 {len(recorded)} 个，全部完成的 {sum(done)} 个。")
    print(f"已写入 {target.name}（{len(text)} 个字符）。")
    return 0 if all(done) else 1


def _turn(session: Session, line: Line, index: int) -> dict[str, Any]:
    """录一个回合：用户的消息照场景给，每次批准请求都按这个回合的做法回应。

    场景要批准的回合里，只有场景点名的操作才放行；真实模型临时想到的别的操作按拒绝处理。
    """
    decisions: list[Decision] = []
    notes: list[str] = []

    def ask(pending: Pending) -> None:
        notes.append(pending.note)
        decision: Decision = line.policy
        if decision == "approved" and not pointed_out(index, pending):
            decision = "rejected"
            print("拦下了一次场景没有点名的请求，按拒绝处理。")
        decisions.append(decision)
        session.respond_action(pending.call_id, decision)

    result = session.start_turn(line.message, ask=ask)
    print(f"\n== 回合：{line.message}")
    print(f"结局：{result.outcome.value}（{result.reason or '没有原因要写'}）")
    for note in notes:
        print(f"批准提示（{line.policy}）：\n{note}")
    print(f"最终回复：{result.reply}")
    return {
        "message": line.message,
        "policy": line.policy,
        "decisions": decisions,
        "outcome": result.outcome.value,
    }


@contextmanager
def _recording(config: ModelConfig, on_response: Any) -> Iterator[OpenAI]:
    with httpx2.Client(event_hooks={"response": [on_response]}) as http:
        yield OpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
            max_retries=0,
            http_client=http,
        )


def _fixture_text(
    config: ModelConfig, name: str, tmp: str, scenario: Scenario, recorded: list[dict[str, Any]]
) -> str | None:
    """拼出夹具的文本；里面有密钥、接口地址或本机路径时不写，返回 None。"""
    fixture = {
        # 行数门禁凭第一行里的 @generated 认出这是生成文件：它是录下来的数据，不要手改。
        "generated": GENERATED,
        "recorded": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": config.model,
        "source": (
            f"uv run python -m tests.integration.record_provider {name} 的一次运行："
            "真实接口，经正式的回合入口。"
        ),
        "instruction_sha256": hashlib.sha256(SYSTEM_INSTRUCTION.encode()).hexdigest(),
        "workdir": scenario.workdir,
        "turns": recorded,
    }
    text = json.dumps(fixture, ensure_ascii=False, indent=2) + "\n"
    for private in (config.api_key, config.base_url, tmp, str(Path.home())):
        if private and private in text:
            print("夹具里出现了不该入库的内容（密钥、接口地址或本机路径），没有写入。")
            return None
    return text


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in SCENARIOS:
        raise SystemExit(
            f"用法：python -m tests.integration.record_provider <{'|'.join(SCENARIOS)}>"
        )
    raise SystemExit(main(sys.argv[1]))
