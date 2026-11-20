"""属性测试（不变量验证）。

判定表覆盖的是「我以为会出问题的地方」，剩下的组合靠人想不全。
这里换个思路：不写具体期望值，只写**任何一张订单都必须成立的性质**，
然后随机造一千笔订单去撞。

这类测试的价值不在「找到已知 bug」，而在「找到我没有想到的 bug」。
随机必须固定种子 —— 否则今天红明天绿，出了问题没法复现。
"""

from __future__ import annotations

import random

import pytest

from app.coupon_engine import Coupon, Item, calc

SEED = 20271120
PRICES = [500, 1000, 3000, 5000, 9900, 12800, 20000, 50000, 100000]
OFFS = [500, 1000, 2000, 3000, 5000, 10000]


def gen_order(rng: random.Random) -> tuple[list[Item], list[Coupon]]:
    items = [
        Item(
            name=f"商品{i}",
            category=rng.choice(["ceramic", "other"]),
            price_cents=rng.choice(PRICES),
            qty=rng.randint(1, 3),
            is_special=rng.random() < 0.2,
        )
        for i in range(rng.randint(1, 3))
    ]

    kind = rng.choice(["none", "full", "discount", "category", "newuser"])
    if kind == "none":
        return items, []
    if kind == "full":
        return items, [Coupon(code="F", kind="full_reduction", threshold_cents=rng.choice([9900, 20000]), off_cents=rng.choice(OFFS))]
    if kind == "discount":
        return items, [Coupon(code="D", kind="discount", rate=rng.choice([70, 85, 90, 95]), cap_cents=rng.choice([None, 3000, 5000]))]
    if kind == "category":
        return items, [Coupon(code="C", kind="category", threshold_cents=rng.choice([5000, 10000]), off_cents=rng.choice(OFFS), category="ceramic")]
    return items, [Coupon(code="N", kind="newuser", off_cents=rng.choice(OFFS))]


def check_invariants(items: list[Item], coupons: list[Coupon]) -> list[str]:
    """一笔订单无论怎么组合，这四条必须成立。"""
    r = calc(items, coupons)
    problems: list[str] = []

    if r.payable < 0:
        problems.append(f"应付金额为负：{r.payable}（商品 {r.goods_total}，优惠 {r.discount}）")

    if r.discount < 0:
        problems.append(f"优惠金额为负：{r.discount}")

    if r.discount > r.goods_total:
        problems.append(f"优惠 {r.discount} 超过商品金额 {r.goods_total}")

    if r.payable + r.discount != r.goods_total + r.shipping:
        problems.append(
            f"金额不守恒：应付 {r.payable} + 优惠 {r.discount} "
            f"!= 商品 {r.goods_total} + 运费 {r.shipping}"
        )

    return problems


@pytest.mark.xfail(
    strict=True,
    reason="BUG-003：优惠总额超过商品金额时没有截断，随机订单里出现了负的应付金额。",
)
def test_invariants_hold_over_1000_orders():
    rng = random.Random(SEED)
    violations: list[str] = []

    for _ in range(1000):
        items, coupons = gen_order(rng)
        for problem in check_invariants(items, coupons):
            desc = ", ".join(f"{i.name}:{i.price_cents}×{i.qty}" + ("(特价)" if i.is_special else "") for i in items)
            coupon_desc = ",".join(f"{c.code}({c.kind},{c.off_cents or c.rate})" for c in coupons) or "无券"
            violations.append(f"[{desc} | {coupon_desc}] {problem}")

    if violations:
        sample = "\n".join(f"  - {v}" for v in violations[:5])
        pytest.fail(f"1000 笔随机订单里有 {len(violations)} 处违反不变量：\n{sample}")


@pytest.mark.xfail(strict=True, reason="BUG-003：小订单用大额券会算出负应付，真实场景就是倒贴钱。")
def test_invariants_on_extreme_small_orders():
    """小而贵的券：这类订单在真实系统里就是「倒贴钱」事故的来源。"""
    violations = []
    for price in (500, 1000, 2000, 3000):
        for off in (3000, 5000, 10000):
            items = [Item(name="小件", category="other", price_cents=price, qty=1)]
            coupons = [Coupon(code="N", kind="newuser", off_cents=off)]
            for problem in check_invariants(items, coupons):
                violations.append(f"[{price} 分订单用 {off} 分券] {problem}")

    if violations:
        sample = "\n".join(f"  - {v}" for v in violations[:5])
        pytest.fail(f"极端小订单有 {len(violations)} 处违反不变量：\n{sample}")
