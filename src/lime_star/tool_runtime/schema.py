"""JSON Schema 的一个子集，够用来校验工具参数。

只解释四个关键字：type、properties、required、items。工具的参数模式只用这些关键字；
别的一律不认，也不报错。
"""

from collections.abc import Mapping

from lime_star.protocol import Json

_NAMES = {
    "object": "对象",
    "array": "数组",
    "string": "字符串",
    "integer": "整数",
    "number": "数字",
    "boolean": "布尔值",
    "null": "空值",
}
"""各种类型在说明里的叫法。说明是给模型看的。"""


def problem(schema: Mapping[str, Json], value: Json, where: str = "参数") -> str | None:
    """按模式检查一个值，返回第一处不符合的地方；没有问题时返回 None。"""
    expected = schema.get("type")
    if expected is not None and not _matches(expected, value):
        names = "或".join(_NAMES.get(kind, kind) for kind in _kinds(expected))
        return f"{where}：应当是{names}，实际是{_NAMES[_kind_of(value)]}"
    members = _object(value)
    if members is not None:
        required = schema.get("required")
        if isinstance(required, list):
            for name in required:
                if name not in members:
                    return f"缺少必填的{where}：{name}"
        properties = _object(schema.get("properties"))
        if properties is not None:
            for name, sub in properties.items():
                pattern = _object(sub)
                if pattern is not None and name in members:
                    found = problem(pattern, members[name], f"{where} {name}")
                    if found is not None:
                        return found
    if isinstance(value, list):
        items = _object(schema.get("items"))
        if items is not None:
            for index, element in enumerate(value, start=1):
                found = problem(items, element, f"{where} 的第 {index} 项")
                if found is not None:
                    return found
    return None


def _object(value: Json) -> dict[str, Json] | None:
    return value if isinstance(value, dict) else None


def _kinds(expected: Json) -> list[str]:
    if isinstance(expected, str):
        return [expected]
    if isinstance(expected, list):
        return [kind for kind in expected if isinstance(kind, str)]
    return []


def _matches(expected: Json, value: Json) -> bool:
    return any(_is(kind, value) for kind in _kinds(expected))


def _is(kind: str, value: Json) -> bool:
    if kind == "object":
        return isinstance(value, dict)
    if kind == "array":
        return isinstance(value, list)
    if kind == "string":
        return isinstance(value, str)
    if kind in ("integer", "number"):
        # 真值在 Python 里也是整数，先排除掉。
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "null":
        return value is None
    return True


def _kind_of(value: Json) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return "null"
