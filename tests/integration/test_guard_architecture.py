"""架构守卫（技术债 CCD-002、CCD-003）：依赖方向与 Owner 章节的确认块。

两件事都在仓库自身上检查，不启动任何进程：
1. src/lime_star 下每个包的导入不超出 architecture.md 第 4 节的依赖矩阵，
   模型客户端 SDK 只出现在 model_provider。
2. architecture.md 第 7 节的每个 Owner 章节都带一份填写完整并已签署的确认块。
守卫自己也要能被证伪：下面的用例用临时目录里的违例树和合成文档，验证它确实会报出来。
verify-local 的 architecture 任务在产品代码、架构图或本文件变动时执行本文件。
"""

import ast
import re
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
ARCHITECTURE = REPO / "internal" / "aiprompts" / "architecture.md"
SOURCE = REPO / "src" / "lime_star"
ROOT_PACKAGE = "lime_star"
MODEL_PACKAGE = "model_provider"
MODEL_SDK = "openai"

_MATRIX_ROW = re.compile(r"^\|\s*`([a-z_]+)`\s*\|\s*(.*?)\s*\|\s*$", re.MULTILINE)
_CHAPTER = re.compile(r"^### (7\.\d+) (.+)$", re.MULTILINE)
_BLOCK = re.compile(r"```text\n(.*?)\n```", re.DOTALL)
_FIELDS = ("Architecture impact", "架构图已更新", "Responsible developer confirmation", "确认内容")
_PLACEHOLDER = re.compile(r"[<>]|待确认|待填写|TODO|TBD")
_SIGNED = re.compile(r"^(?P<name>[^,，]+?)[,，]\s*(?P<day>\d{4}-\d{2}-\d{2})$")


def section(doc: str, number: int) -> str:
    """第 number 节的正文：从它的二级标题到下一个二级标题之前。没有这一节时返回空串。"""
    for part in re.split(r"(?m)^## ", doc):
        if part.startswith(f"{number}. "):
            return part
    return ""


def allowed_imports(doc: str) -> dict[str, frozenset[str]]:
    """从第 4 节的表里读出依赖矩阵：包 -> 它允许导入的本项目包。读不到时抛 ValueError。"""
    matrix: dict[str, frozenset[str]] = {}
    for name, allowed in _MATRIX_ROW.findall(section(doc, 4)):
        names = [] if allowed == "无" else [part.strip(" `") for part in allowed.split("、")]
        matrix[name] = frozenset(names)
    if not matrix:
        raise ValueError("architecture.md 第 4 节里没有找到依赖矩阵。")
    return matrix


def import_problems(source: Path, matrix: dict[str, frozenset[str]]) -> list[str]:
    """逐个文件检查导入，返回违例说明。source 的一级子目录是一个包。"""
    problems: list[str] = []
    for path in sorted(source.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        shown = _shown(source, path)
        parts = path.relative_to(source).parts
        package = parts[0] if len(parts) > 1 else ""
        if package and package not in matrix:
            problems.append(
                f"{shown}：包 {package} 没有在 architecture.md 第 4 节的依赖矩阵里登记，"
                "先登记再写代码"
            )
            continue
        allowed = matrix.get(package, frozenset())
        allowed_text = "、".join(sorted(allowed)) if allowed else "无"
        holder = package or "根包"
        for lineno, module in _imports(path, [ROOT_PACKAGE, *parts[:-1]]):
            target = _target(module)
            if _is_sdk(module) and package != MODEL_PACKAGE:
                problems.append(
                    f"{shown}:{lineno}：模型客户端 SDK（{MODEL_SDK}）只能出现在 {MODEL_PACKAGE}"
                )
            # 导入自己包里的模块不算依赖。
            elif target is not None and target != package and target not in allowed:
                problems.append(
                    f"{shown}:{lineno}：{holder}：不得导入 {module}（只允许导入 {allowed_text}）"
                )
    return problems


def _shown(source: Path, path: Path) -> str:
    """违例说明里的文件路径：从 source 上两级的目录算起，仓库自身就是 src/lime_star/... 的形式。"""
    try:
        return path.relative_to(source.parents[1]).as_posix()
    except ValueError:
        return path.as_posix()


def _imports(path: Path, package: list[str]) -> Iterator[tuple[int, str]]:
    """文件里的每一个导入：行号和模块名。相对导入按文件所在的包解析。"""
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name
        elif isinstance(node, ast.ImportFrom):
            base = package[: len(package) - (node.level - 1)] if node.level else []
            if node.module:
                base = [*base, *node.module.split(".")]
            yield node.lineno, ".".join(base)


def _is_sdk(module: str) -> bool:
    return module == MODEL_SDK or module.startswith(MODEL_SDK + ".")


def _target(module: str) -> str | None:
    """模块属于本项目的哪个包；根包和本项目之外的模块返回 None。"""
    if not module.startswith(ROOT_PACKAGE + "."):
        return None
    return module.split(".")[1]


def confirmation_problems(doc: str) -> list[str]:
    """第 7 节里每个 Owner 章节的确认块。

    缺块、缺行、占位、未签署、引用不存在的章节、内容不全，都算问题。
    """
    problems: list[str] = []
    text = section(doc, 7)
    sections = {int(number) for number in re.findall(r"(?m)^## (\d+)\. ", doc)}
    starts = list(_CHAPTER.finditer(text))
    for index, start in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
        label = f"Owner 章节 {start[1]} {start[2]}"
        problems.extend(_block_problems(label, text[start.end() : end], sections))
    return problems


def _block_problems(label: str, body: str, sections: set[int]) -> list[str]:
    blocks = _BLOCK.findall(body)
    if len(blocks) != 1:
        return [f"{label}：必须有且只有一份 text 代码块形式的确认块，实际 {len(blocks)} 份"]
    fields: dict[str, str] = {}
    for line in blocks[0].split("\n"):
        if not line.strip():
            continue
        found = re.match(r"^([^:：]+)[:：]\s*(.*)$", line)
        if found is None:
            return [f"{label}：确认块里有无法解析的行：{line!r}"]
        fields[found[1].strip()] = found[2].strip()
    if tuple(fields) != _FIELDS:
        return [f"{label}：确认块必须依次有四行：{', '.join(_FIELDS)}"]
    problems = []
    if fields[_FIELDS[0]] != "major":
        problems.append(f"{label}：{_FIELDS[0]} 必须是 major")
    updated = fields[_FIELDS[1]]
    referenced = re.search(r"第 (\d+) 节", updated)
    if referenced is None or int(referenced[1]) not in sections or _PLACEHOLDER.search(updated):
        problems.append(
            f"{label}：{_FIELDS[1]} 必须指向本文件里存在的一节（写成“第 N 节”），"
            f"实际是：{updated or '空'}"
        )
    problems.extend(_signature_problems(label, fields[_FIELDS[2]]))
    problems.extend(_content_problems(label, fields[_FIELDS[3]]))
    return problems


def _signature_problems(label: str, value: str) -> list[str]:
    signed = _SIGNED.match(value)
    if signed is None or _PLACEHOLDER.search(signed["name"]):
        return [
            f"{label}：{_FIELDS[2]} 必须写成“<姓名/代号>, <日期>”并由责任开发者签署，"
            f"实际是：{value or '空'}"
        ]
    try:
        date.fromisoformat(signed["day"])
    except ValueError:
        return [f"{label}：{_FIELDS[2]} 里的日期不是真实日期：{signed['day']}"]
    return []


def _content_problems(label: str, value: str) -> list[str]:
    if not value or _PLACEHOLDER.search(value):
        return [f"{label}：{_FIELDS[3]} 不能为空，也不能留着占位符"]
    return [
        f"{label}：{_FIELDS[3]} 必须说明替代方案与回滚策略，现在没有提到“{word}”"
        for word in ("替代", "回滚")
        if word not in value
    ]


MATRIX = {
    "cli": frozenset({"app", "protocol"}),
    "app": frozenset({"agent_runtime", "model_provider", "tool_runtime", "protocol"}),
    "agent_runtime": frozenset({"protocol"}),
    "model_provider": frozenset({"protocol"}),
    "tool_runtime": frozenset({"protocol"}),
    "thread_store": frozenset({"protocol"}),
    "protocol": frozenset(),
}
"""一份合成的依赖矩阵，和仓库架构图里的那张相同。"""


def make_source(base: Path, files: dict[str, str]) -> Path:
    """在临时目录里搭一棵 src/lime_star 树。"""
    source = base / "src" / "lime_star"
    for relative, text in files.items():
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return source


def test_imports_follow_the_dependency_matrix() -> None:
    """在仓库自身上检查：src/lime_star 下的导入没有违例。"""
    matrix = allowed_imports(ARCHITECTURE.read_text(encoding="utf-8"))
    assert import_problems(SOURCE, matrix) == []


def test_the_matrix_is_read_from_the_architecture_doc() -> None:
    matrix = allowed_imports(ARCHITECTURE.read_text(encoding="utf-8"))
    assert set(matrix) == set(MATRIX)
    assert matrix["cli"] == MATRIX["cli"]
    assert matrix["agent_runtime"] == MATRIX["agent_runtime"]
    assert matrix["protocol"] == frozenset()
    with pytest.raises(ValueError, match="依赖矩阵"):
        allowed_imports("## 4. 依赖方向\n\n这一节没有表。\n")


def test_the_cli_cannot_bypass_the_app(tmp_path: Path) -> None:
    source = make_source(
        tmp_path, {"cli/main.py": "from lime_star.model_provider import Provider\n"}
    )
    [problem] = import_problems(source, MATRIX)
    assert (
        problem == "src/lime_star/cli/main.py:1："
        "cli：不得导入 lime_star.model_provider（只允许导入 app、protocol）"
    )


def test_allowed_imports_pass(tmp_path: Path) -> None:
    source = make_source(
        tmp_path,
        {
            "__init__.py": "__version__ = '0'\n",
            "cli/main.py": (
                "from lime_star import __version__\nfrom lime_star.app import open_session\n"
            ),
            "app/session.py": (
                "import lime_star.agent_runtime\nfrom lime_star.model_provider import Provider\n"
            ),
            "agent_runtime/loop.py": "from lime_star.protocol import Item\n",
            "model_provider/provider.py": "import openai\nfrom openai import OpenAI\n",
        },
    )
    assert import_problems(source, MATRIX) == []


def test_the_model_sdk_stays_inside_the_model_boundary(tmp_path: Path) -> None:
    source = make_source(
        tmp_path,
        {
            "agent_runtime/loop.py": "import openai\n",
            "model_provider/provider.py": "from openai import OpenAI\n",
        },
    )
    assert import_problems(source, MATRIX) == [
        "src/lime_star/agent_runtime/loop.py:1：模型客户端 SDK（openai）只能出现在 model_provider"
    ]


def test_a_package_missing_from_the_matrix_is_reported(tmp_path: Path) -> None:
    source = make_source(tmp_path, {"extra/x.py": "import json\n"})
    [problem] = import_problems(source, MATRIX)
    assert (
        problem == "src/lime_star/extra/x.py："
        "包 extra 没有在 architecture.md 第 4 节的依赖矩阵里登记，先登记再写代码"
    )


def test_relative_and_nested_imports_are_resolved_before_checking(tmp_path: Path) -> None:
    source = make_source(
        tmp_path,
        {
            "agent_runtime/loop.py": "def run():\n    from ..tool_runtime import Registry\n",
            "thread_store/store.py": "from ..protocol import Item\n",
        },
    )
    [problem] = import_problems(source, MATRIX)
    assert (
        problem == "src/lime_star/agent_runtime/loop.py:2："
        "agent_runtime：不得导入 lime_star.tool_runtime（只允许导入 protocol）"
    )


def test_the_root_package_cannot_import_a_subpackage(tmp_path: Path) -> None:
    source = make_source(tmp_path, {"__init__.py": "from lime_star.cli import main\n"})
    [problem] = import_problems(source, MATRIX)
    assert problem == "src/lime_star/__init__.py:1：根包：不得导入 lime_star.cli（只允许导入 无）"


def document(chapter: str) -> str:
    """一份合成的架构图：一到六节是占位，第七节放一个 Owner 章节。"""
    body = "".join(f"## {number}. 第 {number} 节\n\n正文。\n\n" for number in range(1, 8))
    return body + "### 7.1 回合循环\n\n" + chapter


SIGNED = "\n".join(
    [
        "```text",
        "Architecture impact: major",
        "架构图已更新：architecture.md 第 2 节目录地图",
        "Responsible developer confirmation: 仓库所有者，2026-11-24",
        "确认内容：本阶段落地回合循环。替代方案：由 CLI 直接驱动模型。"
        "回滚策略：删除 agent_runtime 目录。",
        "```",
    ]
)
CHAPTER = "Owner 章节 7.1 回合循环"


def test_owner_chapters_carry_a_signed_confirmation_block() -> None:
    """在仓库自身上检查：第 7 节的每个 Owner 章节都有填写完整并已签署的确认块。"""
    assert confirmation_problems(ARCHITECTURE.read_text(encoding="utf-8")) == []


def test_a_signed_block_passes() -> None:
    assert confirmation_problems(document(SIGNED)) == []
    assert confirmation_problems("## 7. Owner 章节\n\n暂无。\n") == []


def test_a_chapter_without_a_block_is_reported() -> None:
    assert confirmation_problems(document("只有正文。")) == [
        f"{CHAPTER}：必须有且只有一份 text 代码块形式的确认块，实际 0 份"
    ]
    twice = confirmation_problems(document(SIGNED + "\n\n" + SIGNED))
    assert [problem.rsplit("，", 1)[1] for problem in twice] == ["实际 2 份"]


def test_a_block_with_a_missing_line_is_reported() -> None:
    broken = SIGNED.replace("架构图已更新：architecture.md 第 2 节目录地图\n", "")
    [problem] = confirmation_problems(document(broken))
    assert problem == (f"{CHAPTER}：确认块必须依次有四行：{', '.join(_FIELDS)}")


@pytest.mark.parametrize(
    ("old", "new", "field"),
    [
        ("仓库所有者，2026-11-24", "待确认", "Responsible developer confirmation"),
        ("仓库所有者，2026-11-24", "<姓名/代号>, 2026-11-24", "Responsible developer confirmation"),
        ("仓库所有者，2026-11-24", "仓库所有者", "Responsible developer confirmation"),
        ("仓库所有者，2026-11-24", "仓库所有者，2026-13-40", "Responsible developer confirmation"),
        ("architecture.md 第 2 节目录地图", "第 9 节", "架构图已更新"),
        ("architecture.md 第 2 节目录地图", "", "架构图已更新"),
        ("Architecture impact: major", "Architecture impact: minor", "Architecture impact"),
        (
            "替代方案：由 CLI 直接驱动模型。回滚策略：删除 agent_runtime 目录。",
            "没有交代。",
            "确认内容",
        ),
        ("替代方案：由 CLI 直接驱动模型。", "", "确认内容"),
    ],
)
def test_an_unfinished_block_is_reported_against_its_field(old: str, new: str, field: str) -> None:
    """没签署、留着占位符、日期不存在、引用了没有的节、内容缺替代方案或回滚策略：各报在各那一行上。"""
    problems = confirmation_problems(document(SIGNED.replace(old, new)))
    assert problems
    assert all(problem.startswith(f"{CHAPTER}：{field}") for problem in problems)
