"""判定表数据加载器。

数据在 `data/coupon_cases.yaml`，这里只做两件事：读、校验。

**为什么必须校验类型**：从 YAML 读进来的"整数"可能是字符串（`"12800"`）、
浮点（`128.00`）或带千分位（`12,800`）。金额一旦变成浮点，`calc()` 算出来就是浮点，
断言会以一个很难看懂的方式失败——期望 `12800`，实际 `12800.0`，看起来一样却不等。

这个坑我在旧项目 api-framework 里踩过一次：YAML 里写 `int`，读出来是字符串，
`isinstance(x, int)` 直接抛 `TypeError: isinstance() arg 2 must be a type`。
当时是在断言层加 TYPE_MAP 修的，这次把校验前移到加载层，错的数据进不来。
"""

from __future__ import annotations

import pathlib

import yaml

DATA_FILE = pathlib.Path(__file__).resolve().parents[1] / "data" / "coupon_cases.yaml"

REQUIRED = ("id", "desc", "items", "coupons", "payable", "discount")
TOP_INT_FIELDS = ("payable", "discount", "shipping")
ITEM_INT_FIELDS = ("price_cents", "qty")


def _to_int(value, where: str) -> int:
    """把 YAML 里的"看起来像整数"的值转成 int，转不了就报错并指出是哪条用例。"""
    if isinstance(value, bool):  # bool 是 int 子类，必须先拦
        raise TypeError(f"{where} 应为整数，实际是布尔值 {value!r}")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not value.is_integer():
            raise ValueError(f"{where} 应为整数（分），实际是小数 {value!r}")
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.replace(",", "").replace("_", "").strip())
        except ValueError as exc:
            raise ValueError(f"{where} 应为整数（分），实际是字符串 {value!r}") from exc
    raise TypeError(f"{where} 应为整数，实际是 {type(value).__name__}")


def load_cases(path: pathlib.Path | None = None) -> list[dict]:
    path = path or DATA_FILE
    rows = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"{path.name} 应是非空列表，实际是 {type(rows).__name__}")

    cases: list[dict] = []
    seen: set[str] = set()

    for index, row in enumerate(rows, start=1):
        missing = [key for key in REQUIRED if key not in row]
        if missing:
            raise ValueError(f"第 {index} 条缺少字段 {missing}")

        case_id = row["id"]
        if case_id in seen:
            raise ValueError(f"重复的 id：{case_id}")
        seen.add(case_id)

        for field in TOP_INT_FIELDS:
            if field in row:
                row[field] = _to_int(row[field], f"{case_id}.{field}")

        for item in row["items"]:
            for field in ITEM_INT_FIELDS:
                item[field] = _to_int(item.get(field, 1), f"{case_id}.items.{field}")

        cases.append(row)

    return cases
