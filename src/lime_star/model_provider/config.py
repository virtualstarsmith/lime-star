"""模型配置：地址、密钥和模型名从哪里读、怎样算缺（需求 R4.1、R4.2，决策 D-01）。"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

BASE_URL_VAR = "LIME_STAR_BASE_URL"
API_KEY_VAR = "LIME_STAR_API_KEY"
MODEL_VAR = "LIME_STAR_MODEL"

ENV_FILE = ".env"
EXAMPLE_FILE = ".env.example"

_VARIABLES = (BASE_URL_VAR, API_KEY_VAR, MODEL_VAR)
_SCHEMES = frozenset({"http", "https"})
# 密钥只允许不含空白的可打印 ASCII。别的字符会让 SDK 抛出带请求头的异常。
_KEY_CHARS = frozenset(chr(code) for code in range(0x21, 0x7F))


class ConfigError(Exception):
    """模型配置缺项或不合法。消息只写变量名和原因，不回显配置的值。"""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class ModelConfig:
    """一次会话使用的模型配置。"""

    base_url: str
    api_key: str
    model: str


def load_config(env: Mapping[str, str], workdir: Path) -> ModelConfig:
    """环境变量优先；缺项时读工作目录下的 .env，且只读这一个位置。"""
    values = {name: env.get(name, "").strip() for name in _VARIABLES}
    if not all(values.values()):
        for name, value in _read_env_file(workdir / ENV_FILE).items():
            if name in values and not values[name]:
                values[name] = value
    missing = [name for name in _VARIABLES if not values[name]]
    if missing:
        raise ConfigError(
            f"缺少模型配置：{'、'.join(missing)}。"
            f"请设置这些环境变量，或在 {ENV_FILE} 里填写（样例见 {EXAMPLE_FILE}）。"
        )
    return ModelConfig(
        base_url=_checked_url(values[BASE_URL_VAR]),
        api_key=_checked_key(values[API_KEY_VAR]),
        model=values[MODEL_VAR],
    )


def _read_env_file(path: Path) -> dict[str, str]:
    """解析 NAME=VALUE 行。值两端的成对引号会被去掉，其他变量名的行被忽略。"""
    if not path.is_file():
        return {}
    try:
        text = path.read_bytes().decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ConfigError(f"{ENV_FILE} 不是合法的 UTF-8 文件。") from exc
    values: dict[str, str] = {}
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name, sep, value = line.partition("=")
        if not sep or not name.strip():
            raise ConfigError(f"{ENV_FILE} 第 {number} 行无法解析：应当写成 NAME=VALUE。")
        values[name.strip()] = _unquote(value.strip())
    return values


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _checked_url(value: str) -> str:
    try:
        parts = urlsplit(value)
        valid = parts.scheme in _SCHEMES and bool(parts.netloc)
    except ValueError:
        valid = False
    if not valid:
        raise ConfigError(
            f"{BASE_URL_VAR} 必须是 http 或 https 地址，例如 https://api.example.com/v1。"
        )
    return value


def _checked_key(value: str) -> str:
    if not _KEY_CHARS.issuperset(value):
        raise ConfigError(f"{API_KEY_VAR} 含有空白或不可打印的字符。")
    return value
