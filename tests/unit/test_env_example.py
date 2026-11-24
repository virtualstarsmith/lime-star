"""仓库里的 .env.example：只含变量名和占位值（需求 R4.4）。"""

import re
from pathlib import Path

from lime_star.model_provider import API_KEY_VAR, BASE_URL_VAR, MODEL_VAR

EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"
PLACEHOLDER = re.compile(r"^LIME_STAR_[A-Z_]+=<[^=]*>$")


def test_env_example_has_only_names_and_placeholders() -> None:
    """R4.4-S1：三个必需的变量各占一行，值都是尖括号里的占位说明，没有任何真实值。"""
    lines = EXAMPLE.read_text(encoding="utf-8").splitlines()
    assert [line.split("=", 1)[0] for line in lines] == [BASE_URL_VAR, API_KEY_VAR, MODEL_VAR]
    assert all(PLACEHOLDER.match(line) for line in lines), lines
