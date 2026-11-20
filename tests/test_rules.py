"""优惠券规则测试 —— 判定表驱动。

每条用例就是判定表里的一行：条件（商品、券、金额）→ 期望动作（减多少、能不能用）。
表在 `data/coupon_cases.yaml`，测试文件只负责把行变成 Item/Coupon 再断言——
新增一个组合只加一段 YAML，不用碰这里的代码（类型校验见 `tests/case_loader.py`）。
"""

from __future__ import annotations

import pytest

from app.coupon_engine import Coupon, Item, calc
from case_loader import load_cases

# 其他品类商品：用来验证「品类券不能被别的东西凑单」
OTHER = {"name": "竹制杯垫", "category": "other", "price_cents": 5000, "qty": 1}


def cup(price_cents: int, qty: int = 1, special: bool = False) -> dict:
    return {
        "name": "测试杯",
        "category": "ceramic",
        "price_cents": price_cents,
        "qty": qty,
        "is_special": special,
    }


CASES = load_cases()


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_decision_table(case):
    items = [Item(**i) for i in case["items"]]
    coupons = [Coupon(**c) for c in case["coupons"]]

    result = calc(items, coupons)

    assert result.payable == case["payable"], (
        f'{case["id"]}｜{case["desc"]}｜期望应付 {case["payable"]}，实际 {result.payable}'
    )
    assert result.discount == case["discount"], (
        f'{case["id"]}｜期望优惠 {case["discount"]}，实际 {result.discount}'
    )
    if "shipping" in case:
        assert result.shipping == case["shipping"]
    for code in case.get("applied", []):
        assert code in result.applied, f'{case["id"]}｜{code} 应生效'
    for code in case.get("rejected", []):
        assert code in result.rejected, f'{case["id"]}｜{code} 应被拒绝'


# ============================================================
# 互斥与冲突：这类规则用正例测不出来，必须专门写反例
# ============================================================


class TestConflict:
    def test_discount_cannot_stack_with_full_reduction(self):
        with pytest.raises(ValueError, match="折扣券不能"):
            calc(
                [Item(**cup(20000))],
                [
                    Coupon(code="D85", kind="discount", rate=85),
                    Coupon(code="F200", kind="full_reduction", threshold_cents=20000, off_cents=3000),
                ],
            )

    def test_only_one_full_reduction(self):
        with pytest.raises(ValueError, match="同类券只能用一张"):
            calc(
                [Item(**cup(30000))],
                [
                    Coupon(code="F200", kind="full_reduction", threshold_cents=20000, off_cents=3000),
                    Coupon(code="F300", kind="full_reduction", threshold_cents=30000, off_cents=5000),
                ],
            )

    def test_empty_order_is_rejected(self):
        with pytest.raises(ValueError, match="订单不能为空"):
            calc([], [])


# ============================================================
# 以下三条对应已提缺陷，见 03-缺陷记录.md
# 修好之后把 xfail 标记删掉，用例会自动变成「验证通过的回归用例」
# ============================================================


@pytest.mark.xfail(strict=True, reason="BUG-001：品类券门槛用整单金额判断，其他品类凑单也能用。")
def test_category_threshold_counts_only_category_items():
    """陶瓷只有 50 元，其他品类 60 元，整单 110 —— 不应该能用「陶瓷满 100」的券。"""
    result = calc(
        [Item(**cup(5000)), Item(**OTHER)],
        [Coupon(code="C100", kind="category", threshold_cents=10000, off_cents=2000, category="ceramic")],
    )
    assert "C100" in result.rejected, f"整单 110 但陶瓷只有 50，券不该生效，实际 applied={result.applied}"


@pytest.mark.xfail(strict=True, reason="BUG-002：满减门槛把运费算进去了。")
def test_full_reduction_threshold_excludes_shipping():
    """商品 90 元 + 12 元运费 = 102 元 —— 不该满足「商品满 100 减 10」。"""
    result = calc(
        [Item(**cup(9000))],
        [Coupon(code="F100", kind="full_reduction", threshold_cents=10000, off_cents=1000)],
    )
    assert result.payable == 10200, f"运费不该计入门槛，实际应付 {result.payable}"


@pytest.mark.xfail(strict=True, reason="BUG-003：优惠超过商品金额时没有截断，应付变成负数。")
def test_discount_never_exceeds_goods_total():
    """30 元订单用 50 元新人券，最多减到 0，不能倒贴。"""
    result = calc(
        [Item(**cup(3000))],
        [Coupon(code="N50", kind="newuser", off_cents=5000)],
    )
    assert result.payable >= 0, f"应付金额不能为负，实际 {result.payable}"


# ============================================================
# 边界值：02-测试设计.md 的边界表里列了，但判定表没落地的临界点
# ============================================================


class TestBoundary:
    """包邮门槛 9900 和折扣封顶这两组临界，原来只在文档里写了，代码里没测。

    边界值只写在文档里、不落成用例，等于没测：文档说测了，代码里查不到。
    """

    def test_free_shipping_just_below_threshold(self):
        result = calc([Item(**cup(9899))], [])
        assert result.shipping == 1200, "差 1 分不包邮"
        assert result.payable == 11099

    def test_free_shipping_exactly_on_threshold(self):
        result = calc([Item(**cup(9900))], [])
        assert result.shipping == 0, "刚好 99 元应包邮"
        assert result.payable == 9900

    def test_free_shipping_just_above_threshold(self):
        result = calc([Item(**cup(9901))], [])
        assert result.shipping == 0
        assert result.payable == 9901

    def test_discount_cap_boundary_not_reached(self):
        """333.34 元 × 15% = 5000.1 分，向下取整正好 5000，刚好等于封顶、还没被截断。"""
        result = calc(
            [Item(**cup(33334))],
            [Coupon(code="D85", kind="discount", rate=85, cap_cents=5000)],
        )
        assert result.discount == 5000
        assert result.payable == 28334

    def test_discount_cap_boundary_takes_effect(self):
        """333.40 元 × 15% = 5001 分，应被 50 元封顶截到 5000。"""
        result = calc(
            [Item(**cup(33340))],
            [Coupon(code="D85", kind="discount", rate=85, cap_cents=5000)],
        )
        assert result.discount == 5000, f"封顶应生效，实际减 {result.discount}"
        assert result.payable == 28340


@pytest.mark.xfail(strict=True, reason="BUG-004：R9 要求同类券只能用一张，实现只限制了满减券，品类券可以叠两张。")
def test_same_kind_category_coupons_should_be_rejected():
    """需求 R9：同一类型的券只能用一张。两张陶瓷品类券不能同时生效。"""
    with pytest.raises(ValueError, match="同类券只能用一张"):
        calc(
            [Item(**cup(30000))],
            [
                Coupon(code="C1", kind="category", threshold_cents=10000, off_cents=2000, category="ceramic"),
                Coupon(code="C2", kind="category", threshold_cents=10000, off_cents=1000, category="ceramic"),
            ],
        )
